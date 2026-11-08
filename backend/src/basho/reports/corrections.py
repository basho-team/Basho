"""Correções do pesquisador/gerente aplicadas como nova versão rastreável.

Regras:
- a correção declara a versão-base; se não for a atual → `VersionConflictError` (409);
- a versão anterior nunca é alterada; aprovações anteriores não passam para a nova;
- experimentos (inclusive negativos/inconclusivos) não podem ser removidos; mudar o desfecho
  exige evidência e motivo;
- afirmação só vira `supported` com evidência citada; resposta sem evidência mantém `pending`
  (o schema `ReportClaim` garante isso);
- o resultado é revalidado integralmente por `ResearchReportDraft`.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from basho.agent.artifacts import (
    ClaimSection,
    ClaimStatus,
    ExperimentOutcomeKind,
    ResearchReportDraft,
)
from basho.reports.versions import ChangeRecord, ReportVersion, ensure_current

MIN_REASON_LENGTH = 10


class _Op(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ReviseClaim(_Op):
    """Substitui a afirmação no índice dado (texto, status e campos do status)."""

    kind: Literal["revise_claim"] = "revise_claim"
    claim_index: int = Field(ge=0)
    text: str
    status: ClaimStatus
    evidence_ids: tuple[UUID, ...] = ()
    question: str | None = None
    ask_role: str | None = None
    dispute_reason: str | None = None


class AddClaim(_Op):
    kind: Literal["add_claim"] = "add_claim"
    section: ClaimSection
    text: str
    status: ClaimStatus
    evidence_ids: tuple[UUID, ...] = ()
    question: str | None = None
    ask_role: str | None = None
    dispute_reason: str | None = None


class WithdrawClaim(_Op):
    """Retira uma afirmação incorreta; o motivo fica no registro de mudança."""

    kind: Literal["withdraw_claim"] = "withdraw_claim"
    claim_index: int = Field(ge=0)
    reason: str = Field(min_length=MIN_REASON_LENGTH)


class ReviseExperimentOutcome(_Op):
    """Muda o desfecho declarado de um experimento. Nunca remove o experimento."""

    kind: Literal["revise_experiment_outcome"] = "revise_experiment_outcome"
    experiment_index: int = Field(ge=0)
    outcome: ExperimentOutcomeKind
    evidence_ids: tuple[UUID, ...] = Field(min_length=1)
    reason: str = Field(min_length=MIN_REASON_LENGTH)


class AddExperiment(_Op):
    kind: Literal["add_experiment"] = "add_experiment"
    description: str
    outcome: ExperimentOutcomeKind
    evidence_ids: tuple[UUID, ...] = Field(min_length=1)


class ResolveMissing(_Op):
    """Encerra uma lacuna de `missing[]` com evidência que a responde.

    Lacuna `formal_hours` só se resolve por referência a eventos `FORMAL_HOURS_DECLARED`
    (`formal_hours_event_ids`); nunca por número informado no texto.
    """

    kind: Literal["resolve_missing"] = "resolve_missing"
    missing_index: int = Field(ge=0)
    evidence_ids: tuple[UUID, ...] = ()
    formal_hours_event_ids: tuple[UUID, ...] = ()


CorrectionOp = Annotated[
    ReviseClaim
    | AddClaim
    | WithdrawClaim
    | ReviseExperimentOutcome
    | AddExperiment
    | ResolveMissing,
    Field(discriminator="kind"),
]

FORMAL_HOURS_FIELD = "formal_hours"


class ReportCorrection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    base_version_id: UUID = Field(description="Versão exata que o autor corrigiu")
    author_id: UUID
    author_role: str = Field(min_length=1)
    reason: str = Field(min_length=MIN_REASON_LENGTH)
    operations: tuple[CorrectionOp, ...] = Field(min_length=1)


class InvalidCorrectionError(ValueError):
    """Operação incompatível com a versão-base (índice inexistente, regra violada)."""


def apply_correction(
    history: Sequence[ReportVersion],
    correction: ReportCorrection,
    *,
    new_version_id: UUID,
    created_at: datetime,
) -> ReportVersion:
    """Gera a versão N+1 a partir da versão atual. Não altera nenhuma versão existente."""
    base = ensure_current(history, correction.base_version_id)
    data = base.draft.model_dump(mode="python")
    data["missing"] = list(data["missing"])
    claims: list[dict[str, Any] | None] = list(data["claims"])
    affected_claims: set[int] = set()
    affected_experiments: set[int] = set()
    summaries: list[str] = []
    for op in correction.operations:
        summaries.append(_apply_op(op, data, claims, affected_claims, affected_experiments))
    data["claims"] = [claim for claim in claims if claim is not None]
    data["missing"] = [item for item in data["missing"] if item is not None]
    try:
        draft = ResearchReportDraft.model_validate(data)
    except ValueError as exc:
        raise InvalidCorrectionError(f"correção gera relatório inválido: {exc}") from exc
    return ReportVersion(
        id=new_version_id,
        tenant_id=base.tenant_id,
        number=base.number + 1,
        draft=draft,
        supersedes_id=base.id,
        change=ChangeRecord(
            author_id=correction.author_id,
            author_role=correction.author_role,
            reason=correction.reason,
            operations=tuple(summaries),
            affected_claims=tuple(sorted(affected_claims)),
            affected_experiments=tuple(sorted(affected_experiments)),
        ),
        created_at=created_at,
        is_synthetic=base.is_synthetic,
    )


def _claim_payload(op: ReviseClaim | AddClaim, section: Any) -> dict[str, Any]:
    return {
        "section": section,
        "text": op.text,
        "status": op.status,
        "evidence_ids": op.evidence_ids,
        "question": op.question,
        "ask_role": op.ask_role,
        "dispute_reason": op.dispute_reason,
    }


def _check_index(index: int, items: Sequence[Any], label: str) -> None:
    if index >= len(items) or items[index] is None:
        raise InvalidCorrectionError(f"{label} {index} não existe na versão-base")


def _apply_op(
    op: CorrectionOp,
    data: dict[str, Any],
    claims: list[dict[str, Any] | None],
    affected_claims: set[int],
    affected_experiments: set[int],
) -> str:
    if isinstance(op, ReviseClaim):
        _check_index(op.claim_index, claims, "afirmação")
        current = claims[op.claim_index]
        assert current is not None  # noqa: S101 — garantido por _check_index
        claims[op.claim_index] = _claim_payload(op, current["section"])
        affected_claims.add(op.claim_index)
        return f"revise_claim[{op.claim_index}] → {op.status.value}"
    if isinstance(op, AddClaim):
        claims.append(_claim_payload(op, op.section))
        affected_claims.add(len(claims) - 1)
        return f"add_claim[{len(claims) - 1}] {op.section.value}"
    if isinstance(op, WithdrawClaim):
        _check_index(op.claim_index, claims, "afirmação")
        claims[op.claim_index] = None
        affected_claims.add(op.claim_index)
        return f"withdraw_claim[{op.claim_index}]: {op.reason}"
    if isinstance(op, (ReviseExperimentOutcome, AddExperiment)):
        return _apply_experiment_op(op, data, affected_experiments)
    return _apply_resolve_missing(op, data)


def _apply_experiment_op(
    op: ReviseExperimentOutcome | AddExperiment,
    data: dict[str, Any],
    affected: set[int],
) -> str:
    experiments: list[dict[str, Any]] = list(data["experiments"])
    if isinstance(op, AddExperiment):
        experiments.append(
            {"description": op.description, "outcome": op.outcome, "evidence_ids": op.evidence_ids}
        )
        affected.add(len(experiments) - 1)
        data["experiments"] = experiments
        return f"add_experiment[{len(experiments) - 1}] {op.outcome.value}"
    _check_index(op.experiment_index, experiments, "experimento")
    previous = experiments[op.experiment_index]
    merged = tuple(dict.fromkeys((*previous["evidence_ids"], *op.evidence_ids)))
    experiments[op.experiment_index] = {**previous, "outcome": op.outcome, "evidence_ids": merged}
    affected.add(op.experiment_index)
    data["experiments"] = experiments
    old = ExperimentOutcomeKind(previous["outcome"]).value
    return f"revise_experiment[{op.experiment_index}] {old} → {op.outcome.value}: {op.reason}"


def _apply_resolve_missing(op: ResolveMissing, data: dict[str, Any]) -> str:
    missing: list[dict[str, Any] | None] = data["missing"]
    _check_index(op.missing_index, missing, "lacuna")
    item = missing[op.missing_index]
    assert item is not None  # noqa: S101 — garantido por _check_index
    is_hours = item["field"] == FORMAL_HOURS_FIELD
    if is_hours and not op.formal_hours_event_ids:
        msg = "lacuna formal_hours só se resolve com formal_hours_event_ids (evento formal)"
        raise InvalidCorrectionError(msg)
    if not is_hours and op.formal_hours_event_ids:
        msg = "formal_hours_event_ids só se aplica à lacuna formal_hours"
        raise InvalidCorrectionError(msg)
    if not is_hours and not op.evidence_ids:
        raise InvalidCorrectionError("lacuna só se resolve com evidência citada")
    if is_hours:
        current = tuple(data["formal_hours_event_ids"])
        data["formal_hours_event_ids"] = tuple(
            dict.fromkeys((*current, *op.formal_hours_event_ids))
        )
    missing[op.missing_index] = None
    refs = ",".join(str(e) for e in (*op.evidence_ids, *op.formal_hours_event_ids))
    return f"resolve_missing[{op.missing_index}] {item['field']} ← {refs}"
