"""Correções do pesquisador/gerente aplicadas como nova versão rastreável.

Regras:
- a correção declara a versão-base; se não for a atual → `VersionConflictError` (409);
- operações referenciam itens por **ID estável** (`claim_id`, `experiment_id`, `missing_id`),
  nunca por posição; a versão anterior nunca é alterada;
- experimentos (inclusive negativos/inconclusivos) não podem ser removidos; mudar o desfecho
  exige evidência e motivo;
- afirmação só vira `supported` com evidência citada (schema `ReportClaim`);
- lacuna resolvida fica estruturada em `ChangeRecord.resolved_gaps`;
- o resultado é revalidado integralmente por `ResearchReportDraft`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
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
from basho.reports.versions import (
    ChangeRecord,
    ItemKind,
    ReportVersion,
    ResolvedGap,
    WithdrawnClaim,
    ensure_current,
    item_id,
)

MIN_REASON_LENGTH = 10
FORMAL_HOURS_FIELD = "formal_hours"


class _Op(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class _ClaimFields(_Op):
    text: str
    status: ClaimStatus
    evidence_ids: tuple[UUID, ...] = ()
    question: str | None = None
    ask_role: str | None = None
    dispute_reason: str | None = None


class ReviseClaim(_ClaimFields):
    """Substitui o conteúdo da afirmação; a seção e o ID são preservados."""

    kind: Literal["revise_claim"] = "revise_claim"
    claim_id: UUID


class AddClaim(_ClaimFields):
    kind: Literal["add_claim"] = "add_claim"
    section: ClaimSection


class WithdrawClaim(_Op):
    """Retira uma afirmação incorreta; o motivo fica estruturado no registro de mudança."""

    kind: Literal["withdraw_claim"] = "withdraw_claim"
    claim_id: UUID
    reason: str = Field(min_length=MIN_REASON_LENGTH)


class ReviseExperimentOutcome(_Op):
    """Muda o desfecho declarado de um experimento. Nunca remove o experimento."""

    kind: Literal["revise_experiment_outcome"] = "revise_experiment_outcome"
    experiment_id: UUID
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
    (`formal_hours_event_ids`); nunca por número informado no texto. A conferência do tipo do
    evento no ledger é dependência (#9/#39).
    """

    kind: Literal["resolve_missing"] = "resolve_missing"
    missing_id: UUID
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


class ReportCorrection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    base_version_id: UUID = Field(description="Versão exata que o autor corrigiu")
    author_id: UUID
    author_role: str = Field(min_length=1)
    reason: str = Field(min_length=MIN_REASON_LENGTH)
    operations: tuple[CorrectionOp, ...] = Field(min_length=1)


class InvalidCorrectionError(ValueError):
    """Operação incompatível com a versão-base (ID inexistente, regra violada)."""


@dataclass
class _Work:
    """Estado mutável local durante a aplicação; nunca sai desta função."""

    new_version_id: UUID
    claims: dict[UUID, dict[str, Any]]
    experiments: dict[UUID, dict[str, Any]]
    missing: dict[UUID, dict[str, Any]]
    formal_hours: list[UUID]
    summaries: list[str] = field(default_factory=list)
    affected_claims: list[UUID] = field(default_factory=list)
    added_claims: list[UUID] = field(default_factory=list)
    withdrawn: list[WithdrawnClaim] = field(default_factory=list)
    affected_experiments: list[UUID] = field(default_factory=list)
    added_experiments: list[UUID] = field(default_factory=list)
    resolved: list[ResolvedGap] = field(default_factory=list)


def apply_correction(
    history: Sequence[ReportVersion],
    correction: ReportCorrection,
    *,
    new_version_id: UUID,
    created_at: datetime,
) -> ReportVersion:
    """Gera a versão N+1 a partir da versão atual. Não altera nenhuma versão existente."""
    base = ensure_current(history, correction.base_version_id)
    dumped = base.draft.model_dump(mode="python")
    work = _Work(
        new_version_id=new_version_id,
        claims=dict(zip(base.claim_ids, dumped["claims"], strict=True)),
        experiments=dict(zip(base.experiment_ids, dumped["experiments"], strict=True)),
        missing=dict(zip(base.missing_ids, dumped["missing"], strict=True)),
        formal_hours=list(dumped["formal_hours_event_ids"]),
    )
    for op in correction.operations:
        work.summaries.append(_apply_op(op, work))
    data = {
        **dumped,
        "claims": list(work.claims.values()),
        "experiments": list(work.experiments.values()),
        "missing": list(work.missing.values()),
        "formal_hours_event_ids": tuple(dict.fromkeys(work.formal_hours)),
    }
    try:
        draft = ResearchReportDraft.model_validate(data)
    except ValueError as exc:
        raise InvalidCorrectionError(f"correção gera relatório inválido: {exc}") from exc
    return ReportVersion(
        id=new_version_id,
        tenant_id=base.tenant_id,
        number=base.number + 1,
        draft=draft,
        claim_ids=tuple(work.claims),
        experiment_ids=tuple(work.experiments),
        missing_ids=tuple(work.missing),
        supersedes_id=base.id,
        change=_change_record(correction, work),
        created_at=created_at,
        is_synthetic=base.is_synthetic,
    )


def _change_record(correction: ReportCorrection, work: _Work) -> ChangeRecord:
    return ChangeRecord(
        author_id=correction.author_id,
        author_role=correction.author_role,
        reason=correction.reason,
        operations=tuple(work.summaries),
        affected_claim_ids=tuple(dict.fromkeys(work.affected_claims)),
        added_claim_ids=tuple(work.added_claims),
        withdrawn=tuple(work.withdrawn),
        affected_experiment_ids=tuple(dict.fromkeys(work.affected_experiments)),
        added_experiment_ids=tuple(work.added_experiments),
        resolved_gaps=tuple(work.resolved),
    )


def _require(items: dict[UUID, dict[str, Any]], key: UUID, label: str) -> dict[str, Any]:
    if key not in items:
        raise InvalidCorrectionError(f"{label} {key} não existe na versão-base")
    return items[key]


def _claim_payload(op: _ClaimFields, section: Any) -> dict[str, Any]:
    return {
        "section": section,
        "text": op.text,
        "status": op.status,
        "evidence_ids": op.evidence_ids,
        "question": op.question,
        "ask_role": op.ask_role,
        "dispute_reason": op.dispute_reason,
    }


def _apply_op(op: CorrectionOp, work: _Work) -> str:
    if isinstance(op, ReviseClaim):
        current = _require(work.claims, op.claim_id, "afirmação")
        work.claims[op.claim_id] = _claim_payload(op, current["section"])
        work.affected_claims.append(op.claim_id)
        return f"revise_claim {op.claim_id} → {op.status.value}"
    if isinstance(op, AddClaim):
        new_id = item_id(work.new_version_id, ItemKind.CLAIM, len(work.added_claims))
        work.claims[new_id] = _claim_payload(op, op.section)
        work.added_claims.append(new_id)
        return f"add_claim {new_id} {op.section.value}"
    if isinstance(op, WithdrawClaim):
        _require(work.claims, op.claim_id, "afirmação")
        del work.claims[op.claim_id]
        work.withdrawn.append(WithdrawnClaim(claim_id=op.claim_id, reason=op.reason))
        return f"withdraw_claim {op.claim_id}: {op.reason}"
    if isinstance(op, ReviseExperimentOutcome):
        return _revise_experiment(op, work)
    if isinstance(op, AddExperiment):
        new_id = item_id(work.new_version_id, ItemKind.EXPERIMENT, len(work.added_experiments))
        work.experiments[new_id] = {
            "description": op.description,
            "outcome": op.outcome,
            "evidence_ids": op.evidence_ids,
        }
        work.added_experiments.append(new_id)
        return f"add_experiment {new_id} {op.outcome.value}"
    return _resolve_missing(op, work)


def _revise_experiment(op: ReviseExperimentOutcome, work: _Work) -> str:
    previous = _require(work.experiments, op.experiment_id, "experimento")
    merged = tuple(dict.fromkeys((*previous["evidence_ids"], *op.evidence_ids)))
    work.experiments[op.experiment_id] = {
        **previous,
        "outcome": op.outcome,
        "evidence_ids": merged,
    }
    work.affected_experiments.append(op.experiment_id)
    old = ExperimentOutcomeKind(previous["outcome"]).value
    return f"revise_experiment {op.experiment_id} {old} → {op.outcome.value}: {op.reason}"


def _resolve_missing(op: ResolveMissing, work: _Work) -> str:
    item = _require(work.missing, op.missing_id, "lacuna")
    is_hours = item["field"] == FORMAL_HOURS_FIELD
    if is_hours and not op.formal_hours_event_ids:
        msg = "lacuna formal_hours só se resolve com formal_hours_event_ids (evento formal)"
        raise InvalidCorrectionError(msg)
    if not is_hours and op.formal_hours_event_ids:
        raise InvalidCorrectionError("formal_hours_event_ids só se aplica à lacuna formal_hours")
    if not is_hours and not op.evidence_ids:
        raise InvalidCorrectionError("lacuna só se resolve com evidência citada")
    work.formal_hours.extend(op.formal_hours_event_ids)
    del work.missing[op.missing_id]
    work.resolved.append(
        ResolvedGap(
            missing_id=op.missing_id,
            field=item["field"],
            evidence_ids=op.evidence_ids,
            formal_hours_event_ids=op.formal_hours_event_ids,
        )
    )
    return f"resolve_missing {op.missing_id} {item['field']}"
