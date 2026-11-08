"""Adaptador relatório → análise fiscal (proposta; integração local de #43 + frente fiscal).

Implementa os critérios de aceite de `docs/proposals/report-origin-fiscal-review.md`:
1. resolve cada item pelo localizador (versão + tipo + ID) dentro do escopo autorizado e
   rejeita escopo, versão ou pesquisador divergentes;
2. a revisão aplicada é recuperada pelo ID exato; só a revisão do **pesquisador-autor** conta
   como confirmação de texto; aprovação de texto nunca confirma despesa nem elegibilidade;
3. v2 não herda a aprovação da v1 (vem da consolidação); aprovação desatualizada vira lacuna;
4. negativos, inconclusivos, conflitos, perguntas e evidência parcial são preservados; cada
   evidência citada é resolvida por `EvidenceResolver`; ausente, de outro escopo ou substituída
   vira lacuna (nunca suporte);
5. horas nunca vêm do texto: só eventos `FORMAL_HOURS_DECLARED` resolvidos no escopo;
6. o período operacional é comparado ao ano-base fiscal sem substituir um pelo outro.

Não decide enquadramento, não cria `Finding` e não altera relatórios. O `EvidenceResolver`
real (ledger, #4/#39) e a marcação de substituição (#11) são dependências; aqui é um Protocol.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from enum import StrEnum
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from basho.expenses.domain.models import Scope, SourceRef
from basho.reports import (
    ItemKind,
    ManagerConsolidation,
    ReportInput,
    ReportReview,
    ReportVersion,
    ReviewerRole,
    consolidate,
)
from basho.reports import SourceRef as ReportSourceRef

FORMAL_HOURS_KIND = "FORMAL_HOURS_DECLARED"
TEXT_ONLY_NOTE = (
    "Confirmação de texto pelo pesquisador não confirma despesa, horas nem elegibilidade; "
    "material para análise humana."
)
Origin = Literal["user", "formal_system", "document", "github"]


class ResolvedEvidence(BaseModel):
    """Evento imutável do ledger resolvido por serviço autorizado (ainda não existe: #39)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    tenant_id: UUID
    project_id: UUID
    kind: str = Field(min_length=1)
    source_ref: str = Field(min_length=1)
    content_hash: str = Field(min_length=1)
    origin: Origin
    superseded_by: UUID | None = None  # preenchido quando #11 existir


class EvidenceResolver(Protocol):
    def resolve(self, evidence_id: UUID) -> ResolvedEvidence | None: ...


class ItemStatus(StrEnum):
    SUPPORTED = "supported"
    PENDING = "pending"
    DISPUTED = "disputed"
    RESULT_POSITIVE = "result_positive"
    RESULT_NEGATIVE = "result_negative"
    RESULT_INCONCLUSIVE = "result_inconclusive"
    GAP = "gap"


class Gap(StrEnum):
    EVIDENCE_UNRESOLVED = "evidence_unresolved"
    EVIDENCE_OUT_OF_SCOPE = "evidence_out_of_scope"
    EVIDENCE_SUPERSEDED = "evidence_superseded"
    NO_EVIDENCE = "no_evidence"
    RESEARCHER_TEXT_REVIEW_MISSING = "researcher_text_review_missing"
    RESEARCHER_APPROVAL_OUTDATED = "researcher_approval_outdated"
    FORMAL_HOURS_MISSING = "formal_hours_missing"
    FORMAL_HOURS_NOT_FORMAL = "formal_hours_not_formal"
    PERIOD_OUTSIDE_FISCAL_YEAR = "period_outside_fiscal_year"
    PERIOD_SPANS_FISCAL_YEARS = "period_spans_fiscal_years"
    OPEN_QUESTION = "open_question"
    EVIDENCE_CONFLICT = "evidence_conflict"


class ReportItemEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    researcher_id: UUID
    version_id: UUID
    item_kind: ItemKind
    item_id: UUID
    status: ItemStatus
    text: str
    sources: tuple[SourceRef, ...]  # só evidências resolvidas, válidas e vigentes
    gaps: tuple[Gap, ...]
    researcher_review_id: UUID | None


class ResearcherDossier(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    researcher_id: UUID
    version_id: UUID
    version_number: int
    researcher_review_id: UUID | None
    formal_hours: tuple[SourceRef, ...]
    gaps: tuple[Gap, ...]


class ReportEvidenceDossier(BaseModel):
    """Insumo para a análise fiscal humana. Não é finding nem decisão."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    scope: Scope
    consolidation_id: UUID
    period_start: date
    period_end: date
    period_gaps: tuple[Gap, ...]
    researchers: tuple[ResearcherDossier, ...]
    items: tuple[ReportItemEvidence, ...]
    note: str = TEXT_ONLY_NOTE


class ScopeMismatchError(ValueError):
    """Relatórios fora do tenant/projeto autorizado: nada é devolvido."""


def build_report_evidence(
    scope: Scope, inputs: Sequence[ReportInput], resolver: EvidenceResolver
) -> ReportEvidenceDossier:
    consolidation = consolidate(inputs)
    if (consolidation.tenant_id, consolidation.project_id) != (scope.tenant_id, scope.project_id):
        raise ScopeMismatchError("relatórios fora do tenant/projeto autorizado")
    by_current_version = {max(i.versions, key=lambda v: v.number).id: i for i in inputs}
    ctx = _Context(scope, resolver)
    researchers = tuple(
        _researcher(consolidation, status_index, by_current_version, ctx)
        for status_index in range(len(consolidation.reports))
    )
    return ReportEvidenceDossier(
        scope=scope,
        consolidation_id=consolidation.consolidation_id,
        period_start=consolidation.period.start,
        period_end=consolidation.period.end,
        period_gaps=_period_gaps(scope, consolidation),
        researchers=researchers,
        items=_items(consolidation, researchers, ctx),
    )


class _Context:
    def __init__(self, scope: Scope, resolver: EvidenceResolver) -> None:
        self.scope = scope
        self.resolver = resolver

    def evidence(self, ids: Sequence[UUID], locator: str) -> tuple[tuple[SourceRef, ...], set[Gap]]:
        sources: list[SourceRef] = []
        gaps: set[Gap] = set()
        for eid in ids:
            resolved = self.resolver.resolve(eid)
            if resolved is None:
                gaps.add(Gap.EVIDENCE_UNRESOLVED)
                continue
            if (resolved.tenant_id, resolved.project_id) != (
                self.scope.tenant_id,
                self.scope.project_id,
            ):
                gaps.add(Gap.EVIDENCE_OUT_OF_SCOPE)
                continue
            if resolved.superseded_by is not None:
                gaps.add(Gap.EVIDENCE_SUPERSEDED)
                continue
            sources.append(self.source_ref(resolved, locator))
        if not ids:
            gaps.add(Gap.NO_EVIDENCE)
        return tuple(sources), gaps

    def source_ref(self, resolved: ResolvedEvidence, locator: str) -> SourceRef:
        return SourceRef(
            tenant_id=self.scope.tenant_id,
            project_id=self.scope.project_id,
            reference=f"evidence:{resolved.id}",
            revision=resolved.content_hash,
            locator=locator,
            origin=resolved.origin,
        )


def _researcher(
    consolidation: ManagerConsolidation,
    index: int,
    by_version: dict[UUID, ReportInput],
    ctx: _Context,
) -> ResearcherDossier:
    status = consolidation.reports[index]
    report = by_version[status.current_version_id]
    current = max(report.versions, key=lambda v: v.number)
    review_id = _verified_researcher_review(current, report.reviews, status.researcher.review_id)
    gaps: list[Gap] = []
    if review_id is None:
        gaps.append(Gap.RESEARCHER_TEXT_REVIEW_MISSING)
    if status.approval_outdated:
        gaps.append(Gap.RESEARCHER_APPROVAL_OUTDATED)
    hours, hour_gaps = _formal_hours(status.formal_hours_event_ids, current, ctx)
    return ResearcherDossier(
        researcher_id=status.researcher_id,
        version_id=current.id,
        version_number=current.number,
        researcher_review_id=review_id,
        formal_hours=hours,
        gaps=(*gaps, *hour_gaps),
    )


def _verified_researcher_review(
    version: ReportVersion, reviews: Sequence[ReportReview], review_id: UUID | None
) -> UUID | None:
    """Critério 2: confirma pelo ID exato que é do autor, no papel researcher, nesta versão."""
    if review_id is None:
        return None
    review = next((r for r in reviews if r.id == review_id), None)
    if review is None:
        return None
    is_author = review.reviewer_id == version.key.researcher_id
    valid = review.reviewer_role is ReviewerRole.RESEARCHER and review.version_id == version.id
    return review.id if is_author and valid else None


def _formal_hours(
    event_ids: Sequence[UUID], version: ReportVersion, ctx: _Context
) -> tuple[tuple[SourceRef, ...], list[Gap]]:
    """Critério 5: só eventos FORMAL_HOURS_DECLARED resolvidos no escopo; nada do texto."""
    if not event_ids:
        return (), [Gap.FORMAL_HOURS_MISSING]
    refs: list[SourceRef] = []
    gaps: list[Gap] = []
    locator = f"report:{version.id}/formal_hours"
    for eid in event_ids:
        sources, evidence_gaps = ctx.evidence((eid,), locator)
        resolved = ctx.resolver.resolve(eid)
        if sources and resolved is not None and resolved.kind == FORMAL_HOURS_KIND:
            refs.extend(sources)
        elif sources:
            gaps.append(Gap.FORMAL_HOURS_NOT_FORMAL)
        gaps.extend(sorted(evidence_gaps))
    return tuple(refs), list(dict.fromkeys(gaps))


def _period_gaps(scope: Scope, consolidation: ManagerConsolidation) -> tuple[Gap, ...]:
    """Critério 6: período operacional ≠ ano-base; só sinaliza a relação entre eles."""
    start, end = consolidation.period.start, consolidation.period.end
    if start.year != end.year:
        return (Gap.PERIOD_SPANS_FISCAL_YEARS,)
    if start.year != scope.fiscal_year:
        return (Gap.PERIOD_OUTSIDE_FISCAL_YEAR,)
    return ()


_RESULT_STATUS = {
    "positive": ItemStatus.RESULT_POSITIVE,
    "negative": ItemStatus.RESULT_NEGATIVE,
    "inconclusive": ItemStatus.RESULT_INCONCLUSIVE,
}


_Row = tuple[ReportSourceRef, ItemStatus, str, tuple[UUID, ...], frozenset[Gap]]


def _rows(c: ManagerConsolidation) -> list[_Row]:
    none: frozenset[Gap] = frozenset()
    rows: list[_Row] = [
        (x.source, ItemStatus.SUPPORTED, x.text, x.evidence_ids, none)
        for x in (*c.advances, *c.result_claims, *c.uncertainties)
    ]
    rows += [
        (r.source, _RESULT_STATUS[r.outcome.value], r.description, r.evidence_ids, none)
        for r in c.results
    ]
    rows += [
        (
            q.source,
            _question_status(q.source.item_kind),
            q.text or q.question,
            q.evidence_ids,
            frozenset({Gap.OPEN_QUESTION}),
        )
        for q in c.open_questions
    ]
    rows += [
        (d.source, ItemStatus.DISPUTED, d.text, d.evidence_ids, frozenset({Gap.EVIDENCE_CONFLICT}))
        for d in c.disputes
    ]
    return rows


def _items(
    c: ManagerConsolidation, researchers: tuple[ResearcherDossier, ...], ctx: _Context
) -> tuple[ReportItemEvidence, ...]:
    """Critérios 1, 3, 4: um registro por item, com evidência resolvida e lacunas explícitas."""
    review_by_version = {r.version_id: r.researcher_review_id for r in researchers}
    items: list[ReportItemEvidence] = []
    for ref, status, text, evidence, extra in _rows(c):
        locator = f"report:{ref.version_id}/{ref.item_kind.value}/{ref.item_id}"
        sources, gaps = ctx.evidence(evidence, locator)
        if ref.item_kind is ItemKind.MISSING:
            gaps.discard(Gap.NO_EVIDENCE)  # lacuna de missing[] já é a própria pendência
        if status is ItemStatus.SUPPORTED and not sources:
            status = ItemStatus.PENDING  # critério 4: sem evidência válida não há suporte
        items.append(
            ReportItemEvidence(
                researcher_id=ref.researcher_id,
                version_id=ref.version_id,
                item_kind=ref.item_kind,
                item_id=ref.item_id,
                status=status,
                text=text,
                sources=sources,
                gaps=tuple(sorted(gaps | extra)),
                researcher_review_id=review_by_version.get(ref.version_id),
            )
        )
    return tuple(items)


def _question_status(kind: ItemKind) -> ItemStatus:
    return ItemStatus.GAP if kind is ItemKind.MISSING else ItemStatus.PENDING
