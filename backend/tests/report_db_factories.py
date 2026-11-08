"""Fábricas para os testes de persistência de reports (dados sintéticos).

O fixture `research_report_draft.json` cita IDs de evidência fixos; aqui eles são trocados por
eventos reais gravados no ledger do tenant/projeto do teste, para passar na checagem de citação.
"""

import json
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from basho.agent.artifacts import ResearchReportDraft
from basho.evidence import EvidenceService
from basho.evidence.contracts import Actor, ActorType, EventSource
from basho.reports import ReportService
from basho.reports.schemas import ReportVersionOut
from evidence_factories import make_event

FIXTURE = Path(__file__).parent / "fixtures" / "research_report_draft.json"
RESEARCHER = UUID("33333333-3333-4333-8333-333333333333")
MAKER = Actor(type=ActorType.AGENT, id="maker", model="test-maker-model")


def _fixture_data() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    data.pop("_synthetic", None)
    return data


def fixture_evidence_ids() -> list[str]:
    data = _fixture_data()
    cited = {eid for claim in data["claims"] for eid in claim["evidence_ids"]}
    cited |= {eid for experiment in data["experiments"] for eid in experiment["evidence_ids"]}
    return sorted(cited)


async def seed_draft(
    session: AsyncSession, tenant_id: UUID, project_id: UUID
) -> ResearchReportDraft:
    """Grava no ledger um evento por evidência do fixture e devolve o draft remapeado."""
    ledger = EvidenceService(session)
    text = FIXTURE.read_text(encoding="utf-8")
    for old_id in fixture_evidence_ids():
        event = await ledger.append(
            make_event(tenant_id=tenant_id, project_id=project_id, source_ref=old_id)
        )
        text = text.replace(old_id, str(event.id))
    data = json.loads(text)
    data.pop("_synthetic", None)
    data["project_id"] = str(project_id)
    return ResearchReportDraft.model_validate(data)


async def seed_report(
    session: AsyncSession, tenant_id: UUID, project_id: UUID
) -> tuple[ResearchReportDraft, ReportVersionOut]:
    draft = await seed_draft(session, tenant_id, project_id)
    created = await ReportService(session).create_report(
        tenant_id, draft, actor=MAKER, source=EventSource.AGENT, is_synthetic=True
    )
    return draft, created
