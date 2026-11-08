"""Fábricas de relatórios e evidências persistidas para os testes de checks e Checker."""

from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

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
from basho.evidence.contracts import Actor, ActorType, EventKind, EventSource, EvidenceEvent
from basho.evidence.domain.hashing import compute_content_hash
from evidence_factories import PROJECT_A, TENANT_A, make_event

RESEARCHER = UUID("00000000-0000-0000-0000-0000000000c1")


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
        "payload": {"researcher_id": str(RESEARCHER), "period": "2026-10"},
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
        researcher_id=RESEARCHER,
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


__all__ = ["PROJECT_A", "RESEARCHER", "TENANT_A", "commit", "formal_hours", "persisted", "report"]
