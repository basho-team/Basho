"""Fábricas de testes (sintéticas): persistência de reports (#39) e checks/Checker/Maker."""

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from basho.agent.artifacts import (
    ClaimSection,
    ClaimStatus,
    ExperimentOutcome,
    ExperimentOutcomeKind,
    Periodicity,
    ReportClaim,
    ReportingPeriod,
    ResearchReportDraft,
)
from basho.evidence import EvidenceService
from basho.evidence.contracts import Actor, ActorType, EventKind, EventSource, EvidenceEvent
from basho.evidence.domain.hashing import compute_content_hash
from basho.reports import ReportService
from basho.reports.schemas import ReportVersionOut
from evidence_factories import PROJECT_A, TENANT_A, make_event

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


CHECKS_RESEARCHER = UUID("00000000-0000-0000-0000-0000000000c1")


def persisted(**overrides: Any) -> EvidenceEvent:
    """Evento como se tivesse saído do ledger (id, hash e data preenchidos)."""
    new = make_event(**overrides)
    return EvidenceEvent(
        **new.model_dump(),
        id=uuid4(),
        content_hash=compute_content_hash(new),
        created_at=datetime.now(UTC),
    )


def commit(
    message: str = "feat: cache de embeddings no pipeline", **overrides: Any
) -> EvidenceEvent:
    return persisted(payload={"message": message, "files": 2}, **overrides)


def formal_hours(**overrides: Any) -> EvidenceEvent:
    fields: dict[str, Any] = {
        "kind": EventKind.FORMAL_HOURS_DECLARED,
        "source": EventSource.USER,
        "source_ref": "timesheet:2026-10",
        "actor": Actor(type=ActorType.USER, id="coordenador-1"),
        "payload": {"researcher_id": str(CHECKS_RESEARCHER), "period": "2026-10"},
    }
    fields.update(overrides)
    return persisted(**fields)


def report(
    *,
    method_text: str = "Testamos cache de embeddings no pipeline de inferência.",
    result_text: str = "O cache não reduziu a latência p95 no benchmark do período.",
    method_ids: tuple[UUID, ...],
    result_ids: tuple[UUID, ...],
    summary: str = "Relatório de outubro: experimento de cache com resultado negativo.",
    formal_hours_event_ids: tuple[UUID, ...] = (),
) -> ResearchReportDraft:
    return ResearchReportDraft(
        project_id=PROJECT_A,
        researcher_id=CHECKS_RESEARCHER,
        period=ReportingPeriod(
            start=date(2026, 10, 1),
            end=date(2026, 10, 31),
            timezone="America/Sao_Paulo",
            periodicity=Periodicity.MONTHLY,
        ),
        summary=summary,
        claims=(
            ReportClaim(
                section=ClaimSection.METHOD,
                text=method_text,
                status=ClaimStatus.SUPPORTED,
                evidence_ids=method_ids,
            ),
            ReportClaim(
                section=ClaimSection.RESULT,
                text=result_text,
                status=ClaimStatus.SUPPORTED,
                evidence_ids=result_ids,
            ),
        ),
        experiments=(
            ExperimentOutcome(
                description="Cache de embeddings no pipeline de inferência",
                outcome=ExperimentOutcomeKind.NEGATIVE,
                evidence_ids=result_ids,
            ),
        ),
        formal_hours_event_ids=formal_hours_event_ids,
    )


__all__ = [
    "CHECKS_RESEARCHER",
    "FIXTURE",
    "MAKER",
    "RESEARCHER",
    "fixture_evidence_ids",
    "seed_draft",
    "seed_report",
    "PROJECT_A",
    "TENANT_A",
    "commit",
    "formal_hours",
    "persisted",
    "report",
]
