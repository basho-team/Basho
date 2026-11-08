"""Versões imutáveis de relatório individual, IDs estáveis de item e revisão por papel.

IDs estáveis de item (proposta, `docs/reports-consolidation.md` §IDs):
- `ResearchReportDraft` (#41) não é alterado; os IDs ficam em tuplas paralelas da versão
  (`claim_ids[i]` ↔ `draft.claims[i]`, idem `experiment_ids` e `missing_ids`).
- Geração determinística: `uuid5(REPORT_ITEM_NAMESPACE, "<versão de origem>/<tipo>/<ordem>")`,
  em que a versão de origem é a que introduziu o item e a ordem é a posição entre os itens
  daquele tipo introduzidos nela. Mesma entrada ⇒ mesmo ID; consolidação nunca cria IDs.
- Correção preserva o ID do item revisado; item retirado some só da versão nova (versões
  antigas mantêm seus IDs); item novo recebe ID derivado da nova versão.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from enum import StrEnum
from itertools import pairwise
from typing import Self
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, model_validator

from basho.agent.artifacts import ResearchReportDraft

FIRST_VERSION = 1
REPORT_ITEM_NAMESPACE = UUID("6f1d3a52-6c2e-5b8e-9a39-6b6173686f72")


class ItemKind(StrEnum):
    CLAIM = "claim"
    EXPERIMENT = "experiment"
    MISSING = "missing"


def item_id(origin_version_id: UUID, kind: ItemKind, ordinal: int) -> UUID:
    """ID estável e determinístico do `ordinal`-ésimo item `kind` introduzido na versão."""
    return uuid5(REPORT_ITEM_NAMESPACE, f"{origin_version_id}/{kind.value}/{ordinal}")


def initial_item_ids(version_id: UUID, draft: ResearchReportDraft) -> dict[str, tuple[UUID, ...]]:
    return {
        "claim_ids": tuple(
            item_id(version_id, ItemKind.CLAIM, i) for i in range(len(draft.claims))
        ),
        "experiment_ids": tuple(
            item_id(version_id, ItemKind.EXPERIMENT, i) for i in range(len(draft.experiments))
        ),
        "missing_ids": tuple(
            item_id(version_id, ItemKind.MISSING, i) for i in range(len(draft.missing))
        ),
    }


class ReportKey(BaseModel):
    """Identidade do relatório individual: projeto + pesquisador + período operacional."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    project_id: UUID
    researcher_id: UUID
    period_start: date
    period_end: date

    @classmethod
    def of(cls, draft: ResearchReportDraft) -> ReportKey:
        return cls(
            project_id=draft.project_id,
            researcher_id=draft.researcher_id,
            period_start=draft.period.start,
            period_end=draft.period.end,
        )


class ResolvedGap(BaseModel):
    """Lacuna de `missing[]` encerrada por uma correção, com as referências que a responderam."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    missing_id: UUID
    field: str
    evidence_ids: tuple[UUID, ...] = ()
    formal_hours_event_ids: tuple[UUID, ...] = ()


class WithdrawnClaim(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    claim_id: UUID
    reason: str = Field(min_length=10)


class ChangeRecord(BaseModel):
    """Por que, por quem e o que mudou em relação à versão anterior (tudo por ID estável)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    author_id: UUID
    author_role: str = Field(min_length=1)
    reason: str = Field(min_length=10)
    operations: tuple[str, ...] = Field(min_length=1, description="Resumo legível")
    affected_claim_ids: tuple[UUID, ...] = ()
    added_claim_ids: tuple[UUID, ...] = ()
    withdrawn: tuple[WithdrawnClaim, ...] = ()
    affected_experiment_ids: tuple[UUID, ...] = ()
    added_experiment_ids: tuple[UUID, ...] = ()
    resolved_gaps: tuple[ResolvedGap, ...] = ()

    @property
    def withdrawn_claim_ids(self) -> tuple[UUID, ...]:
        return tuple(w.claim_id for w in self.withdrawn)


class ReportVersion(BaseModel):
    """Snapshot imutável. Alteração = nova versão com `supersedes_id` (ADR-0003)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    tenant_id: UUID
    number: int = Field(ge=FIRST_VERSION)
    draft: ResearchReportDraft
    claim_ids: tuple[UUID, ...]
    experiment_ids: tuple[UUID, ...]
    missing_ids: tuple[UUID, ...]
    supersedes_id: UUID | None = None
    change: ChangeRecord | None = None
    created_at: datetime
    is_synthetic: bool = False

    @property
    def key(self) -> ReportKey:
        return ReportKey.of(self.draft)

    @model_validator(mode="after")
    def _lineage_and_ids(self) -> Self:
        is_first = self.number == FIRST_VERSION
        if is_first and (self.supersedes_id is not None or self.change is not None):
            raise ValueError("versão 1 não substitui outra nem tem registro de mudança")
        if not is_first and (self.supersedes_id is None or self.change is None):
            raise ValueError("versão > 1 exige supersedes_id e registro de mudança")
        pairs = (
            (self.claim_ids, self.draft.claims, "claim_ids"),
            (self.experiment_ids, self.draft.experiments, "experiment_ids"),
            (self.missing_ids, self.draft.missing, "missing_ids"),
        )
        for ids, items, label in pairs:
            if len(ids) != len(items) or len(set(ids)) != len(ids):
                raise ValueError(f"{label} deve ter um ID único por item do draft")
        return self


def create_first_version(
    *,
    version_id: UUID,
    tenant_id: UUID,
    draft: ResearchReportDraft,
    created_at: datetime,
    is_synthetic: bool = False,
) -> ReportVersion:
    """Cria a versão 1 com IDs de item determinísticos derivados de `version_id`."""
    ids = initial_item_ids(version_id, draft)
    return ReportVersion(
        id=version_id,
        tenant_id=tenant_id,
        number=FIRST_VERSION,
        draft=draft,
        claim_ids=ids["claim_ids"],
        experiment_ids=ids["experiment_ids"],
        missing_ids=ids["missing_ids"],
        created_at=created_at,
        is_synthetic=is_synthetic,
    )


class ReviewDecision(StrEnum):
    """Decisão sobre o **texto** de uma versão.

    `text_approved` confirma redação e fatos daquela versão no papel de quem revisou.
    **Não** é aprovação fiscal, não decide enquadramento e não vale para versões posteriores.
    """

    TEXT_APPROVED = "text_approved"
    CHANGES_REQUESTED = "changes_requested"


class ReviewerRole(StrEnum):
    """Papéis com estado de revisão independente: um não sobrescreve o outro."""

    RESEARCHER = "researcher"
    MANAGER = "manager"


class ReportReview(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    version_id: UUID = Field(description="Versão exata revisada")
    reviewer_id: UUID
    reviewer_role: ReviewerRole
    decision: ReviewDecision
    comment: str | None = None
    reviewed_at: datetime


class VersionConflictError(Exception):
    """Operação sobre versão que não é a atual (semântica HTTP 409)."""

    def __init__(self, requested_id: UUID, current_id: UUID) -> None:
        super().__init__(f"versão {requested_id} não é a atual ({current_id})")
        self.requested_id = requested_id
        self.current_id = current_id


class InvalidHistoryError(ValueError):
    """Histórico de versões incoerente (numeração, cadeia ou relatórios misturados)."""


class ReviewerNotAllowedError(ValueError):
    """Revisão no papel `researcher` por alguém que não é o autor do relatório."""


def validate_history(history: Sequence[ReportVersion]) -> tuple[ReportVersion, ...]:
    """Ordena e confere: mesma chave e tenant, números 1..N contíguos, cadeia `supersedes`."""
    if not history:
        raise InvalidHistoryError("histórico vazio")
    ordered = tuple(sorted(history, key=lambda v: v.number))
    first = ordered[0]
    for expected_number, version in enumerate(ordered, start=FIRST_VERSION):
        if version.number != expected_number:
            raise InvalidHistoryError(f"numeração não contígua em v{version.number}")
        if version.key != first.key or version.tenant_id != first.tenant_id:
            raise InvalidHistoryError("histórico mistura relatórios ou tenants")
    for previous, version in pairwise(ordered):
        if version.supersedes_id != previous.id:
            raise InvalidHistoryError(f"v{version.number} não substitui v{previous.number}")
    return ordered


def current_version(history: Sequence[ReportVersion]) -> ReportVersion:
    return validate_history(history)[-1]


def ensure_current(history: Sequence[ReportVersion], version_id: UUID) -> ReportVersion:
    current = current_version(history)
    if version_id != current.id:
        raise VersionConflictError(version_id, current.id)
    return current


def review_version(
    history: Sequence[ReportVersion],
    *,
    review_id: UUID,
    version_id: UUID,
    reviewer_id: UUID,
    reviewer_role: ReviewerRole,
    decision: ReviewDecision,
    reviewed_at: datetime,
    comment: str | None = None,
) -> ReportReview:
    """Revisão só sobre a versão atual (senão 409); papel `researcher` só pelo próprio autor."""
    current = ensure_current(history, version_id)
    if reviewer_role is ReviewerRole.RESEARCHER and reviewer_id != current.key.researcher_id:
        raise ReviewerNotAllowedError("revisão de pesquisador só pelo autor do relatório")
    return ReportReview(
        id=review_id,
        version_id=version_id,
        reviewer_id=reviewer_id,
        reviewer_role=reviewer_role,
        decision=decision,
        comment=comment,
        reviewed_at=reviewed_at,
    )
