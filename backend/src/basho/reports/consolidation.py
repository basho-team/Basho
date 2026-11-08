"""Consolidação gerencial determinística a partir das versões atuais dos relatórios.

Recebe o histórico de versões e as revisões de cada relatório individual do mesmo tenant,
projeto e período. Usa sempre a **versão atual** e mantém estados de revisão **por papel**
(pesquisador e gerente), com o ID da revisão aplicada. Cada item aponta para a origem por
ID estável (`item_id`) + versão; o contexto de tenant/projeto/período fica só no envelope.
Resultados negativos e inconclusivos entram com o mesmo destaque que os positivos. Não soma
horas nem valores: horas aparecem só como referências a eventos formais.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict

from basho.agent.artifacts import (
    ClaimSection,
    ClaimStatus,
    ExperimentOutcomeKind,
    ReportClaim,
    ReportingPeriod,
)
from basho.reports.versions import (
    REPORT_ITEM_NAMESPACE,
    ItemKind,
    ReportReview,
    ReportVersion,
    ReviewDecision,
    ReviewerRole,
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
    """Origem de um item: (`version_id`, `item_kind`, `item_id`) resolve o item exato.

    `researcher_review_id` é a revisão do pesquisador que aprovou o texto **desta** versão
    (ou `None`). Tenant/projeto/período ficam no envelope `ManagerConsolidation`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    researcher_id: UUID
    version_id: UUID
    version_number: int
    item_kind: ItemKind
    item_id: UUID
    researcher_review_id: UUID | None


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
    """Pergunta pendente; para claims `pending`, traz também o texto e a evidência parcial."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    question: str
    ask_role: str
    topic: str
    text: str | None = None
    evidence_ids: tuple[UUID, ...] = ()
    source: SourceRef


class Dispute(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str
    reason: str
    evidence_ids: tuple[UUID, ...]
    source: SourceRef


class RoleReview(BaseModel):
    """Estado da revisão de um papel sobre a versão atual e o registro que o determinou."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    state: ReviewState
    review_id: UUID | None


class ReportStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    researcher_id: UUID
    current_version_id: UUID
    current_version_number: int
    researcher: RoleReview
    manager: RoleReview
    approved_version_number: int | None  # última versão com texto aprovado pelo pesquisador
    approval_outdated: bool  # pesquisador aprovou versão anterior à atual
    formal_hours_event_ids: tuple[UUID, ...]


class ManagerConsolidation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    consolidation_id: UUID  # determinístico: mesmas entradas ⇒ mesmo ID
    tenant_id: UUID
    project_id: UUID
    period: ReportingPeriod
    input_version_ids: tuple[UUID, ...]
    input_review_ids: tuple[UUID, ...]
    reports: tuple[ReportStatus, ...]
    advances: tuple[ConsolidatedClaim, ...]
    results: tuple[ConsolidatedResult, ...]
    result_claims: tuple[ConsolidatedClaim, ...]
    uncertainties: tuple[ConsolidatedClaim, ...]
    open_questions: tuple[OpenQuestion, ...]
    disputes: tuple[Dispute, ...]
    outcome_counts: dict[ExperimentOutcomeKind, int]
    all_text_approved: bool  # todos os pesquisadores aprovaram o texto da versão atual
    is_synthetic: bool
    note: str = CONSOLIDATION_NOTE


class ReportInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    versions: tuple[ReportVersion, ...]
    reviews: tuple[ReportReview, ...] = ()


class InconsistentConsolidationError(ValueError):
    """Relatórios de escopos diferentes, pesquisador repetido ou revisão órfã."""


def consolidate(inputs: Sequence[ReportInput]) -> ManagerConsolidation:
    if not inputs:
        raise InconsistentConsolidationError("nenhum relatório para consolidar")
    histories = [(validate_history(i.versions), i.reviews) for i in inputs]
    currents = [history[-1] for history, _ in histories]
    _check_same_scope(currents)
    statuses = tuple(_status(history, reviews) for history, reviews in histories)
    parts = _Parts()
    for current, status in zip(currents, statuses, strict=True):
        parts.collect(current, status.researcher)
    first = currents[0]
    version_ids = tuple(sorted(c.id for c in currents))
    review_ids = tuple(sorted(r.id for _, reviews in histories for r in reviews))
    return ManagerConsolidation(
        consolidation_id=_consolidation_id(first.tenant_id, version_ids, review_ids),
        tenant_id=first.tenant_id,
        project_id=first.draft.project_id,
        period=first.draft.period,
        input_version_ids=version_ids,
        input_review_ids=review_ids,
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
        all_text_approved=all(s.researcher.state is ReviewState.TEXT_APPROVED for s in statuses),
        is_synthetic=any(c.is_synthetic for c in currents),
    )


def _consolidation_id(
    tenant_id: UUID, version_ids: tuple[UUID, ...], review_ids: tuple[UUID, ...]
) -> UUID:
    material = f"consolidation/{tenant_id}/{','.join(map(str, version_ids))}/"
    material += ",".join(map(str, review_ids))
    return uuid5(REPORT_ITEM_NAMESPACE, material)


def _check_same_scope(currents: Sequence[ReportVersion]) -> None:
    first = currents[0]
    seen: set[UUID] = set()
    for version in currents:
        same = (
            version.tenant_id == first.tenant_id
            and version.draft.project_id == first.draft.project_id
            and version.draft.period == first.draft.period
        )
        if not same:
            msg = "relatórios de projeto, período ou tenant distintos"
            raise InconsistentConsolidationError(msg)
        if version.key.researcher_id in seen:
            raise InconsistentConsolidationError("pesquisador com mais de um relatório")
        seen.add(version.key.researcher_id)


def _role_review(
    reviews: Sequence[ReportReview], version_id: UUID, role: ReviewerRole
) -> RoleReview:
    own = sorted(
        (r for r in reviews if r.version_id == version_id and r.reviewer_role is role),
        key=lambda r: (r.reviewed_at, str(r.id)),  # desempate estável por ID (mesmo instante)
    )
    if not own:
        return RoleReview(state=ReviewState.AWAITING_REVIEW, review_id=None)
    latest = own[-1]
    return RoleReview(state=ReviewState(latest.decision.value), review_id=latest.id)


def _status(history: tuple[ReportVersion, ...], reviews: Sequence[ReportReview]) -> ReportStatus:
    by_id = {v.id: v for v in history}
    if any(review.version_id not in by_id for review in reviews):
        raise InconsistentConsolidationError("revisão de versão fora do histórico")
    current = history[-1]
    approved = max(
        (
            by_id[r.version_id].number
            for r in reviews
            if r.reviewer_role is ReviewerRole.RESEARCHER
            and r.decision is ReviewDecision.TEXT_APPROVED
        ),
        default=None,
    )
    return ReportStatus(
        researcher_id=current.key.researcher_id,
        current_version_id=current.id,
        current_version_number=current.number,
        researcher=_role_review(reviews, current.id, ReviewerRole.RESEARCHER),
        manager=_role_review(reviews, current.id, ReviewerRole.MANAGER),
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

    def collect(self, version: ReportVersion, researcher: RoleReview) -> None:
        approved_by = (
            researcher.review_id if researcher.state is ReviewState.TEXT_APPROVED else None
        )

        def ref(kind: ItemKind, item: UUID) -> SourceRef:
            return SourceRef(
                researcher_id=version.key.researcher_id,
                version_id=version.id,
                version_number=version.number,
                item_kind=kind,
                item_id=item,
                researcher_review_id=approved_by,
            )

        for cid, claim in zip(version.claim_ids, version.draft.claims, strict=True):
            self._claim(claim.section, claim, ref(ItemKind.CLAIM, cid))
        for eid, exp in zip(version.experiment_ids, version.draft.experiments, strict=True):
            self.results.append(
                ConsolidatedResult(
                    description=exp.description,
                    outcome=exp.outcome,
                    evidence_ids=exp.evidence_ids,
                    source=ref(ItemKind.EXPERIMENT, eid),
                )
            )
        for mid, missing in zip(version.missing_ids, version.draft.missing, strict=True):
            self.questions.append(
                OpenQuestion(
                    question=missing.question,
                    ask_role=missing.ask_role,
                    topic=missing.field,
                    source=ref(ItemKind.MISSING, mid),
                )
            )

    def _claim(self, section: ClaimSection, claim: ReportClaim, source: SourceRef) -> None:
        if claim.status is ClaimStatus.PENDING:
            assert claim.question is not None and claim.ask_role is not None  # noqa: S101
            self.questions.append(
                OpenQuestion(
                    question=claim.question,
                    ask_role=claim.ask_role,
                    topic=section.value,
                    text=claim.text,
                    evidence_ids=claim.evidence_ids,
                    source=source,
                )
            )
            return
        if claim.status is ClaimStatus.DISPUTED:
            assert claim.dispute_reason is not None  # noqa: S101
            self.disputes.append(
                Dispute(
                    text=claim.text,
                    reason=claim.dispute_reason,
                    evidence_ids=claim.evidence_ids,
                    source=source,
                )
            )
            return
        item = ConsolidatedClaim(
            section=section, text=claim.text, evidence_ids=claim.evidence_ids, source=source
        )
        if section is ClaimSection.RESULT:
            self.result_claims.append(item)
        elif section is ClaimSection.UNCERTAINTY:
            self.uncertainties.append(item)
        else:
            self.advances.append(item)
