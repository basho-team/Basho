"""Critérios informados e versionados, sem enquadramento tributário automático."""

from datetime import date
from enum import StrEnum
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from basho.expenses.service import Reconciliation, ReconciliationState, Scope, SourceRef, reconcile


class CriterionReference(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)
    reference: str = Field(min_length=1)
    version: str = Field(min_length=1)
    locator: str = Field(min_length=1)
    checked_on: date


class Criterion(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)
    code: Literal["reconciliation-data-quality"]
    title: str = Field(min_length=1)
    version: str = Field(min_length=1)
    kind: str = Field(pattern=r"^(product_policy|legal_reference)$")
    references: tuple[CriterionReference, ...] = Field(min_length=1)
    applicable_years: tuple[int, ...] = Field(min_length=1)
    valid_from: date
    valid_until: date

    @model_validator(mode="after")
    def ordered_validity(self) -> Self:
        if self.valid_until < self.valid_from:
            raise ValueError("Vigência invertida")
        return self


class Signal(StrEnum):
    INSUFFICIENT_INFORMATION = "insufficient_information"
    POSSIBLE_INCOMPATIBILITY = "possible_incompatibility"
    FISCAL_JUDGMENT_REQUIRED = "fiscal_judgment_required"


class Finding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    scope: Scope
    object_id: UUID
    criterion: Criterion
    signal: Signal
    sources: tuple[SourceRef, ...]
    justification: str
    gaps: tuple[str, ...]
    next_step: str
    assessed_on: date
    eligibility_note: Literal["Potencialmente qualificável, sujeito a análise humana."] = (
        "Potencialmente qualificável, sujeito a análise humana."
    )


_JUSTIFICATIONS = {
    ReconciliationState.CONSISTENT: (
        "Valores e limites declarados são aritmeticamente consistentes; "
        "isso não comprova vínculo com P&D nem enquadramento fiscal."
    ),
    ReconciliationState.PENDING: "Faltam dados ou confirmação para concluir a conciliação.",
    ReconciliationState.CONFLICT: "Fontes do mesmo item econômico divergem.",
    ReconciliationState.DUPLICATE: "Vínculo explícito indica outra representação do mesmo gasto.",
    ReconciliationState.EXCLUDED: "Despesa mantida no histórico com motivo explícito de exclusão.",
}


def prepare_findings(
    reconciliation: Reconciliation, criterion: Criterion, *, assessed_on: date
) -> tuple[Finding, ...]:
    """Uma sinalização por entrada; não aplica automaticamente a lei citada pelo chamador."""
    reconciliation = reconcile(reconciliation.scope, tuple(i.expense for i in reconciliation.items))
    criterion = Criterion.model_validate(criterion.model_dump())
    findings: list[Finding] = []
    scope = reconciliation.scope
    criterion_gaps = _criterion_gaps(criterion, scope, assessed_on)
    for item in reconciliation.items:
        sources = tuple(
            dict.fromkeys(
                (
                    *item.expense.sources,
                    *(s for allocation in item.expense.allocations for s in allocation.sources),
                )
            )
        )
        gaps = (*item.gaps, *criterion_gaps)
        if not sources:
            gaps = (*gaps, "missing_evidence")
        signal = Signal.FISCAL_JUDGMENT_REQUIRED
        if criterion_gaps or item.state == ReconciliationState.PENDING or not sources:
            signal = Signal.INSUFFICIENT_INFORMATION
        elif item.state in {ReconciliationState.CONFLICT, ReconciliationState.DUPLICATE}:
            signal = Signal.POSSIBLE_INCOMPATIBILITY
        if any("exceeds" in gap for gap in item.gaps) and not criterion_gaps:
            signal = Signal.POSSIBLE_INCOMPATIBILITY
        justification = _JUSTIFICATIONS[item.state]
        if item.expense.excluded_reason:
            justification += f" Motivo informado: {item.expense.excluded_reason}"
        if item.duplicate_of:
            justification += f" Referência canônica: {item.duplicate_of}."
        findings.append(
            Finding(
                scope=scope,
                object_id=item.expense.id,
                criterion=criterion,
                signal=signal,
                sources=sources,
                justification=justification,
                gaps=gaps,
                next_step="Revisar fontes e lacunas; registrar decisão humana separadamente.",
                assessed_on=assessed_on,
            )
        )
    return tuple(findings)


def _criterion_gaps(criterion: Criterion, scope: Scope, assessed_on: date) -> tuple[str, ...]:
    gaps: list[str] = []
    if scope.fiscal_year not in criterion.applicable_years:
        gaps.append("criterion_not_verified_for_fiscal_year")
    start, end = date(scope.fiscal_year, 1, 1), date(scope.fiscal_year, 12, 31)
    if criterion.valid_from > start or criterion.valid_until < end:
        gaps.append("criterion_does_not_cover_full_fiscal_year")
    if any(ref.checked_on > assessed_on for ref in criterion.references):
        gaps.append("criterion_reference_checked_after_assessment")
    if criterion.kind == "legal_reference":
        gaps.append("specialist_interpretation_required")
    return tuple(gaps)
