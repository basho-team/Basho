"""Maker com ledger real: consulta de evidências, citação, verificação e eventos persistidos."""

import json
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from basho.agent.approvals import InMemoryApprovalStore
from basho.agent.checks import ReportDeterministicChecker
from basho.agent.ledger_tools import LedgerEvidenceGateway, LedgerQueryEvents
from basho.agent.maker import Maker, MakerStatus, MakerTask
from basho.agent.policy import ToolPolicy
from basho.agent.registry import ToolRegistry
from basho.agent.tasks import RESEARCH_REPORT_PROFILE
from basho.audit import AuditService
from basho.db import tenant_session
from basho.evidence import EvidenceService
from basho.evidence.contracts import Actor, ActorType, ArtifactStatus, EventKind, EventSource
from evidence_factories import make_event
from maker_support import FAKE_MODEL, FakeClient, FixedVerifier, final, report_input, tool_call
from report_factories import report

pytestmark = pytest.mark.db

Factory = async_sessionmaker[AsyncSession]


async def test_maker_cites_real_ledger_evidence_and_persists_events(
    session_factory: Factory,
) -> None:
    # Arrange: um commit observado no ledger de um tenant/projeto novos
    tenant_id, project_id = uuid4(), uuid4()
    async with tenant_session(session_factory, tenant_id) as session:
        observed = await EvidenceService(session).append(
            make_event(tenant_id=tenant_id, project_id=project_id, is_synthetic=True)
        )
    draft = report(method_ids=(observed.id,), result_ids=(observed.id,)).model_copy(
        update={"project_id": project_id}
    )
    client = FakeClient(
        [
            tool_call("ledger_query_events", {"project_id": str(project_id)}),
            final(draft.model_dump_json()),
        ]
    )

    # Act
    async with tenant_session(session_factory, tenant_id) as session:
        evidence = EvidenceService(session)
        registry = ToolRegistry([LedgerQueryEvents(evidence, project_id)])
        maker = Maker(
            client=client,
            registry=registry,
            policy=ToolPolicy(registry, AuditService(session), InMemoryApprovalStore()),
            checker=ReportDeterministicChecker(tenant_id),
            verifier=FixedVerifier(),
            evidence=LedgerEvidenceGateway(evidence),
        )
        result = await maker.run(
            MakerTask(
                tenant_id=tenant_id,
                run_id=uuid4(),
                project_id=project_id,
                profile=RESEARCH_REPORT_PROFILE,
                task_input=report_input(draft),
                is_synthetic=True,
            )
        )

    # Assert
    assert result.status is MakerStatus.COMPLETED
    assert result.outcome is not None
    assert result.outcome.status is ArtifactStatus.VERIFIED
    tool_result = client.messages.requests[1]["messages"][-1]["content"][0]
    listed = json.loads(tool_result["content"])["data"]["events"]
    assert [event["id"] for event in listed] == [str(observed.id)]
    async with tenant_session(session_factory, tenant_id) as session:
        stored = await EvidenceService(session).query(tenant_id, project_id=project_id)
    kinds = {event.kind for event in stored}
    assert kinds == {observed.kind, EventKind.ACTIVITY_RECORD, EventKind.VERIFICATION_RESULT}
    artifact = next(e for e in stored if e.kind is EventKind.ACTIVITY_RECORD)
    assert (artifact.actor.id, artifact.actor.model) == ("maker", FAKE_MODEL)


async def test_ledger_tool_refuses_another_project(session_factory: Factory) -> None:
    # Arrange
    tenant_id, project_id = uuid4(), uuid4()

    # Act
    async with tenant_session(session_factory, tenant_id) as session:
        tool = LedgerQueryEvents(EvidenceService(session), project_id)
        result = await tool.run(str(tenant_id), {"project_id": str(uuid4())})

    # Assert
    assert result.error == "project_not_allowed"


async def test_gateway_skips_evidence_of_another_tenant(session_factory: Factory) -> None:
    # Arrange
    owner, intruder, project_id = uuid4(), uuid4(), uuid4()
    async with tenant_session(session_factory, owner) as session:
        foreign = await EvidenceService(session).append(
            make_event(tenant_id=owner, project_id=project_id)
        )

    # Act
    async with tenant_session(session_factory, intruder) as session:
        found = await LedgerEvidenceGateway(EvidenceService(session)).get_many(
            intruder, project_id, [foreign.id]
        )

    # Assert
    assert found == []


async def test_gateway_skips_evidence_of_another_project(session_factory: Factory) -> None:
    # Arrange
    tenant_id, project_id, other_project = uuid4(), uuid4(), uuid4()
    async with tenant_session(session_factory, tenant_id) as session:
        foreign = await EvidenceService(session).append(
            make_event(tenant_id=tenant_id, project_id=other_project)
        )

    # Act
    async with tenant_session(session_factory, tenant_id) as session:
        found = await LedgerEvidenceGateway(EvidenceService(session)).get_many(
            tenant_id, project_id, [foreign.id]
        )

    # Assert
    assert found == []


async def test_ledger_tool_and_gateway_ignore_agent_events(session_factory: Factory) -> None:
    # Arrange: um rascunho anterior do Maker (source=agent) no mesmo projeto
    tenant_id, project_id = uuid4(), uuid4()
    async with tenant_session(session_factory, tenant_id) as session:
        observed = await EvidenceService(session).append(
            make_event(tenant_id=tenant_id, project_id=project_id)
        )
        previous = await EvidenceService(session).append(
            make_event(
                tenant_id=tenant_id,
                project_id=project_id,
                kind=EventKind.ACTIVITY_RECORD,
                source=EventSource.AGENT,
                actor=Actor(type=ActorType.AGENT, id="maker", model="m"),
                payload={"draft": {}},
            )
        )

    # Act
    async with tenant_session(session_factory, tenant_id) as session:
        evidence = EvidenceService(session)
        listed = await LedgerQueryEvents(evidence, project_id).run(
            str(tenant_id), {"project_id": str(project_id)}
        )
        cited = await LedgerEvidenceGateway(evidence).get_many(
            tenant_id, project_id, [observed.id, previous.id]
        )

    # Assert
    assert listed.data is not None
    assert [event["id"] for event in listed.data["events"]] == [str(observed.id)]
    assert [event.id for event in cited] == [observed.id]


async def test_ledger_tool_never_sends_formal_payload_to_the_model(
    session_factory: Factory,
) -> None:
    # Arrange: horas formais (pessoa + período) não vão ao LLM; só o id para citação
    tenant_id, project_id = uuid4(), uuid4()
    formal_person = "pessoa-formal-123"
    async with tenant_session(session_factory, tenant_id) as session:
        hours = await EvidenceService(session).append(
            make_event(
                tenant_id=tenant_id,
                project_id=project_id,
                kind=EventKind.FORMAL_HOURS_DECLARED,
                source=EventSource.USER,
                actor=Actor(type=ActorType.USER, id="coordenador-1"),
                payload={"researcher_id": formal_person, "period": "2026-10"},
            )
        )

    # Act
    async with tenant_session(session_factory, tenant_id) as session:
        result = await LedgerQueryEvents(EvidenceService(session), project_id).run(
            str(tenant_id), {"project_id": str(project_id)}
        )

    # Assert
    assert result.untrusted_data is not None
    assert formal_person not in result.untrusted_data
    assert str(hours.id) in result.untrusted_data
    assert result.data is not None
    assert result.data["events"][0]["kind"] == "formal_hours_declared"
