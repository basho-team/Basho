"""Versões imutáveis de relatório individual e revisão de texto sobre a versão exata."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from enum import StrEnum
from itertools import pairwise
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from basho.agent.artifacts import ResearchReportDraft

FIRST_VERSION = 1


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


class ChangeRecord(BaseModel):
    """Por que, por quem e o que mudou em relação à versão anterior."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    author_id: UUID
    author_role: str = Field(min_length=1)
    reason: str = Field(min_length=10)
    operations: tuple[str, ...] = Field(min_length=1, description="Resumo de cada operação")
    affected_claims: tuple[int, ...] = ()
    affected_experiments: tuple[int, ...] = ()


class ReportVersion(BaseModel):
    """Snapshot imutável. Alteração = nova versão com `supersedes_id` (ADR-0003)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    tenant_id: UUID
    number: int = Field(ge=FIRST_VERSION)
    draft: ResearchReportDraft
    supersedes_id: UUID | None = None
    change: ChangeRecord | None = None
    created_at: datetime
    is_synthetic: bool = False

    @property
    def key(self) -> ReportKey:
        return ReportKey.of(self.draft)

    @model_validator(mode="after")
    def _lineage(self) -> Self:
        is_first = self.number == FIRST_VERSION
        if is_first and (self.supersedes_id is not None or self.change is not None):
            msg = "versão 1 não substitui outra nem tem registro de mudança"
            raise ValueError(msg)
        if not is_first and (self.supersedes_id is None or self.change is None):
            msg = "versão > 1 exige supersedes_id e registro de mudança"
            raise ValueError(msg)
        return self


class ReviewDecision(StrEnum):
    """Decisão do pesquisador sobre o **texto** de uma versão.

    `text_approved` confirma redação e fatos daquela versão. **Não** é aprovação fiscal,
    não decide enquadramento e não vale para versões posteriores.
    """

    TEXT_APPROVED = "text_approved"
    CHANGES_REQUESTED = "changes_requested"


class ReportReview(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    version_id: UUID = Field(description="Versão exata revisada")
    reviewer_id: UUID
    reviewer_role: str = Field(min_length=1)
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
    reviewer_role: str,
    decision: ReviewDecision,
    reviewed_at: datetime,
    comment: str | None = None,
) -> ReportReview:
    """Registra revisão só sobre a versão atual; versão antiga → `VersionConflictError`."""
    ensure_current(history, version_id)
    return ReportReview(
        id=review_id,
        version_id=version_id,
        reviewer_id=reviewer_id,
        reviewer_role=reviewer_role,
        decision=decision,
        comment=comment,
        reviewed_at=reviewed_at,
    )
