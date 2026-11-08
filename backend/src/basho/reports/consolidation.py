"""Consolidação gerencial determinística a partir das versões atuais dos relatórios.

Recebe o histórico de versões e as revisões de cada relatório individual do mesmo projeto e
período. Usa sempre a **versão atual** e distingue texto aprovado pelo pesquisador de rascunho
pendente. Cada item consolidado aponta para a versão de origem (rastreabilidade). Resultados
negativos e inconclusivos entram com o mesmo destaque que os positivos. Não soma horas nem
valores: horas aparecem só como referências a eventos formais.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from basho.agent.artifacts import (
    ClaimSection,
    ClaimStatus,
    ExperimentOutcomeKind,
    MissingInformation,
)
from basho.reports.versions import (
    ReportReview,
    ReportVersion,
    ReviewDecision,
    validate_history,
)

CONSOLIDATION_NOTE = (
    "Consolidação operacional para acompanhamento gerencial. Não constitui análise, "
    "enquadramento ou aprovação fiscal."
)


class ReviewState(StrEnum):
    TEXT_APPROVED = "text_approved"
    CHANGES_REQUESTED = "changes_requested"
    AWAITING_REVIEW = "awaiting_review"


class SourceRef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    researcher_id: UUID
    version_id: UUID
    version_number: int
    item: str  # ex.: "claims[2]", "experiments[0]", "missing[1]"
    text_approved: bool


class ConsolidatedClaim(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    section: ClaimSection
    text: str
    evidence_ids: tuple[UUID, ...]
    source: SourceRef


class ConsolidatedResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    description: str
    outcome: ExperimentOutcomeKind
    evidence_ids: tuple[UUID, ...]
    source: SourceRef


class OpenQuestion(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    question: str
    ask_role: str
    topic: str
    source: SourceRef


class Dispute(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str
    reason: str
    evidence_ids: tuple[UUID, ...]
    source: SourceRef


class ReportStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    researcher_id: UUID
    current_version_id: UUID
    current_version_number: int
    review_state: ReviewState
    approved_version_number: int | None  # última versão com texto aprovado, se houver
    approval_outdated: bool  # houve aprovação, mas de versão anterior à atual
    formal_hours_event_ids: tuple[UUID, ...]


class ManagerConsolidation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    project_id: UUID
    period_start: date
    period_end: date
    reports: tuple[ReportStatus, ...]
    advances: tuple[ConsolidatedClaim, ...]
    results: tuple[ConsolidatedResult, ...]
    result_claims: tuple[ConsolidatedClaim, ...]
    uncertainties: tuple[ConsolidatedClaim, ...]
    open_questions: tuple[OpenQuestion, ...]
    disputes: tuple[Dispute, ...]
    outcome_counts: dict[ExperimentOutcomeKind, int]
    all_text_approved: bool
    is_synthetic: bool
    note: str = CONSOLIDATION_NOTE


class ReportInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    versions: tuple[ReportVersion, ...]
    reviews: tuple[ReportReview, ...] = ()


class InconsistentConsolidationError(ValueError):
    """Relatórios de projetos/períodos diferentes, pesquisador repetido ou revisão órfã."""


def consolidate(inputs: Sequence[ReportInput]) -> ManagerConsolidation:
    if not inputs:
        raise InconsistentConsolidationError("nenhum relatório para consolidar")
    histories = [(validate_history(i.versions), i.reviews) for i in inputs]
    currents = [history[-1] for history, _ in histories]
    _check_same_scope(currents)
    statuses = tuple(_status(history, reviews) for history, reviews in histories)
    parts = _Parts()
    for current, status in zip(currents, statuses, strict=True):
        parts.collect(current, status.review_state is ReviewState.TEXT_APPROVED)
    first = currents[0].key
    return ManagerConsolidation(
        project_id=first.project_id,
        period_start=first.period_start,
        period_end=first.period_end,
        reports=statuses,
        advances=tuple(parts.advances),
        results=tuple(parts.results),
        result_claims=tuple(parts.result_claims),
        uncertainties=tuple(parts.uncertainties),
        open_questions=tuple(parts.questions),
        disputes=tuple(parts.disputes),
        outcome_counts={
            kind: sum(1 for r in parts.results if r.outcome is kind)
            for kind in ExperimentOutcomeKind
        },
        all_text_approved=all(s.review_state is ReviewState.TEXT_APPROVED for s in statuses),
        is_synthetic=any(c.is_synthetic for c in currents),
    )


def _check_same_scope(currents: Sequence[ReportVersion]) -> None:
    first = currents[0].key
    seen: set[UUID] = set()
    for version in currents:
        key = version.key
        same_scope = (key.project_id, key.period_start, key.period_end) == (
            first.project_id,
            first.period_start,
            first.period_end,
        )
        if not same_scope or version.tenant_id != currents[0].tenant_id:
            raise InconsistentConsolidationError(
                "relatórios de projeto, período ou tenant distintos"
            )
        if key.researcher_id in seen:
            raise InconsistentConsolidationError("pesquisador com mais de um relatório")
        seen.add(key.researcher_id)


def _status(history: tuple[ReportVersion, ...], reviews: Sequence[ReportReview]) -> ReportStatus:
    by_id = {v.id: v for v in history}
    for review in reviews:
        if review.version_id not in by_id:
            raise InconsistentConsolidationError("revisão de versão fora do histórico")
    current = history[-1]
    current_reviews = sorted(
        (r for r in reviews if r.version_id == current.id), key=lambda r: r.reviewed_at
    )
    state = ReviewState.AWAITING_REVIEW
    if current_reviews:
        state = ReviewState(current_reviews[-1].decision.value)
    approved_numbers = [
        by_id[r.version_id].number for r in reviews if r.decision is ReviewDecision.TEXT_APPROVED
    ]
    approved = max(approved_numbers, default=None)
    return ReportStatus(
        researcher_id=current.key.researcher_id,
        current_version_id=current.id,
        current_version_number=current.number,
        review_state=state,
        approved_version_number=approved,
        approval_outdated=approved is not None and approved < current.number,
        formal_hours_event_ids=current.draft.formal_hours_event_ids,
    )


class _Parts:
    def __init__(self) -> None:
        self.advances: list[ConsolidatedClaim] = []
        self.result_claims: list[ConsolidatedClaim] = []
        self.uncertainties: list[ConsolidatedClaim] = []
        self.results: list[ConsolidatedResult] = []
        self.questions: list[OpenQuestion] = []
        self.disputes: list[Dispute] = []

    def collect(self, version: ReportVersion, approved: bool) -> None:
        def ref(item: str) -> SourceRef:
            return SourceRef(
                researcher_id=version.key.researcher_id,
                version_id=version.id,
                version_number=version.number,
                item=item,
                text_approved=approved,
            )

        for i, claim in enumerate(version.draft.claims):
            source = ref(f"claims[{i}]")
            if claim.status is ClaimStatus.PENDING:
                assert claim.question is not None and claim.ask_role is not None  # noqa: S101
                self.questions.append(
                    OpenQuestion(
                        question=claim.question,
                        ask_role=claim.ask_role,
                        topic=claim.section.value,
                        source=source,
                    )
                )
            elif claim.status is ClaimStatus.DISPUTED:
                assert claim.dispute_reason is not None  # noqa: S101
                self.disputes.append(
                    Dispute(
                        text=claim.text,
                        reason=claim.dispute_reason,
                        evidence_ids=claim.evidence_ids,
                        source=source,
                    )
                )
            else:
                self._supported(claim.section, claim.text, claim.evidence_ids, source)
        for i, exp in enumerate(version.draft.experiments):
            self.results.append(
                ConsolidatedResult(
                    description=exp.description,
                    outcome=exp.outcome,
                    evidence_ids=exp.evidence_ids,
                    source=ref(f"experiments[{i}]"),
                )
            )
        for i, missing in enumerate(version.draft.missing):
            self.questions.append(_missing_question(missing, ref(f"missing[{i}]")))

    def _supported(
        self, section: ClaimSection, text: str, evidence: tuple[UUID, ...], source: SourceRef
    ) -> None:
        item = ConsolidatedClaim(section=section, text=text, evidence_ids=evidence, source=source)
        if section is ClaimSection.RESULT:
            self.result_claims.append(item)
        elif section is ClaimSection.UNCERTAINTY:
            self.uncertainties.append(item)
        else:
            self.advances.append(item)


def _missing_question(missing: MissingInformation, source: SourceRef) -> OpenQuestion:
    return OpenQuestion(
        question=missing.question, ask_role=missing.ask_role, topic=missing.field, source=source
    )
