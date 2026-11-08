"""Dossiê fiscal persistido: relatórios do período + evidências do ledger → adaptador puro.

Resolve as evidências citadas pelo `EvidenceService` (tenant da sessão, RLS) e marca como
substituída a evidência que tem um evento posterior com `supersedes` apontando para ela.
Não decide enquadramento nem cria `Finding`: entrega insumo rastreável à análise humana.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from basho.agent.artifacts import ReportingPeriod
from basho.compliance.report_evidence import (
    Origin,
    ReportEvidenceDossier,
    ResolvedEvidence,
    build_report_evidence,
)
from basho.evidence import MAX_PAGE_SIZE, EvidenceNotFoundError, EvidenceService
from basho.evidence.contracts import EventSource, EvidenceEvent
from basho.expenses.domain.models import Scope
from basho.reports import ReportInput
from basho.reports.service import ReportQueryService, cited_evidence_ids

_ORIGINS: dict[EventSource, Origin] = {
    EventSource.GITHUB: "github",
    EventSource.USER: "user",
    EventSource.FORMAL_SYSTEM: "formal_system",
    # Eventos de agente/sistema não são fonte primária: entram como documento derivado.
    EventSource.AGENT: "document",
    EventSource.SYSTEM: "document",
}


class EmptyDossierError(LookupError):
    """Nenhum relatório no projeto/período: não há o que montar."""


class _DictResolver:
    def __init__(self, events: dict[UUID, ResolvedEvidence]) -> None:
        self._events = events

    def resolve(self, evidence_id: UUID) -> ResolvedEvidence | None:
        return self._events.get(evidence_id)


def _resolved(event: EvidenceEvent, superseded_by: UUID | None) -> ResolvedEvidence:
    return ResolvedEvidence(
        id=event.id,
        tenant_id=event.tenant_id,
        project_id=event.project_id,
        kind=event.kind.value.upper(),
        source_ref=event.source_ref or event.kind.value,
        content_hash=event.content_hash,
        origin=_ORIGINS[event.source],
        superseded_by=superseded_by,
    )


class DossierService:
    def __init__(self, session: AsyncSession) -> None:
        self._ledger = EvidenceService(session)
        self._reports = ReportQueryService(session)

    async def build(
        self, tenant_id: UUID, project_id: UUID, period: ReportingPeriod, fiscal_year: int
    ) -> ReportEvidenceDossier:
        inputs = await self._reports.project_inputs(tenant_id, project_id, period)
        if not inputs:
            raise EmptyDossierError("nenhum relatório no projeto e período informados")
        events = await self._resolve(tenant_id, project_id, inputs)
        scope = Scope(tenant_id=tenant_id, project_id=project_id, fiscal_year=fiscal_year)
        return build_report_evidence(scope, inputs, _DictResolver(events))

    async def _resolve(
        self, tenant_id: UUID, project_id: UUID, inputs: list[ReportInput]
    ) -> dict[UUID, ResolvedEvidence]:
        wanted: set[UUID] = set()
        for report in inputs:
            for version in report.versions:
                wanted.update(cited_evidence_ids(version))
        recent = await self._ledger.query(tenant_id, project_id=project_id, limit=MAX_PAGE_SIZE)
        superseded = {e.supersedes: e.id for e in recent if e.supersedes is not None}
        resolved: dict[UUID, ResolvedEvidence] = {}
        for event_id in wanted:
            try:
                event = await self._ledger.get(tenant_id, event_id)
            except EvidenceNotFoundError:
                continue  # o adaptador acusa evidence_unresolved
            resolved[event_id] = _resolved(event, superseded.get(event_id))
        return resolved
