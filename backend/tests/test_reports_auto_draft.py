"""Rascunho automático por regras: só cita fontes do pesquisador; o que falta vira pergunta."""

from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest

from basho.agent.artifacts import ClaimStatus, Periodicity, ReportingPeriod
from basho.agent.checks import ReportDeterministicChecker
from basho.evidence.contracts import (
    Actor,
    ActorType,
    EventKind,
    EventSource,
    EvidenceEvent,
)
from basho.reports.auto_draft import NothingToDraftError, build_auto_draft

TENANT, PROJECT = uuid4(), uuid4()
ANA, BIA = uuid4(), uuid4()
PERIOD = ReportingPeriod(
    start=date(2026, 10, 1),
    end=date(2026, 10, 31),
    timezone="America/Sao_Paulo",
    periodicity=Periodicity.MONTHLY,
)


def _event(kind: EventKind, owner: UUID, **payload: object) -> EvidenceEvent:
    return EvidenceEvent(
        id=uuid4(),
        tenant_id=TENANT,
        project_id=PROJECT,
        kind=kind,
        source=EventSource.GITHUB,
        source_ref="ref",
        actor=Actor(type=ActorType.SYSTEM, id="seed"),
        payload={"researcher_id": str(owner), **payload},
        content_hash="a" * 64,
        created_at=datetime.now(UTC),
    )


def test_cites_only_own_sources_and_opens_questions() -> None:
    pr = _event(
        EventKind.PULL_REQUEST_OBSERVED, ANA, title="PR #42", description="Quantização int8."
    )
    other = _event(EventKind.COMMIT_OBSERVED, BIA, title="b101", description="Calibração.")
    draft = build_auto_draft(PROJECT, ANA, PERIOD, [pr, other])
    cited = {e for c in draft.claims for e in c.evidence_ids}
    assert cited == {pr.id}
    assert any(c.status is ClaimStatus.PENDING for c in draft.claims)
    assert {m.field for m in draft.missing} == {"experiment_outcomes", "formal_hours"}
    assert draft.experiments == ()
    result = ReportDeterministicChecker(TENANT).check(draft, [pr])
    assert result.verdict.value == "pass", result


def test_formal_hours_are_referenced_not_written() -> None:
    pr = _event(
        EventKind.PULL_REQUEST_OBSERVED, ANA, title="PR #42", description="Quantização int8."
    )
    hours = _event(EventKind.FORMAL_HOURS_DECLARED, ANA, title="Horas", hours=96)
    draft = build_auto_draft(PROJECT, ANA, PERIOD, [pr, hours])
    assert draft.formal_hours_event_ids == (hours.id,)
    assert "formal_hours" not in {m.field for m in draft.missing}
    assert all("96" not in c.text for c in draft.claims)


def test_report_version_artifacts_are_not_evidence() -> None:
    artifact = _event(
        EventKind.ACTIVITY_RECORD,
        ANA,
        title="v1",
        artifact="research_report",
        description="Registro da versão do relatório.",
    )
    with pytest.raises(NothingToDraftError):
        build_auto_draft(PROJECT, ANA, PERIOD, [artifact])
