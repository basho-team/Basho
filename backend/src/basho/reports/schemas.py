"""Schemas HTTP de `/api/v1/reports` (#39) sobre os tipos de domínio do PR #43.

Nenhum tipo de domínio é redefinido aqui: versões, revisões, correções e status vêm de
`basho.reports.versions`, `corrections` e `consolidation`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from basho.reports.consolidation import ReportStatus
from basho.reports.corrections import MIN_REASON_LENGTH, CorrectionOp
from basho.reports.versions import ReportReview, ReportVersion, ReviewDecision


class CorrectionIn(BaseModel):
    """Correção enviada com a revisão; vira `ReportCorrection` sobre a versão do path."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reason: str = Field(min_length=MIN_REASON_LENGTH)
    operations: tuple[CorrectionOp, ...] = Field(min_length=1)


class ReviewIn(BaseModel):
    """Revisão humana de uma versão exata (ação formal, ADR-0005).

    `correction` só acompanha `changes_requested` e gera a versão N+1; a versão revisada
    é preservada e a aprovação dela não vale para a nova.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    decision: ReviewDecision
    comment: str | None = Field(default=None, min_length=1)
    correction: CorrectionIn | None = None

    @model_validator(mode="after")
    def _correction_only_with_changes(self) -> Self:
        if self.correction is not None and self.decision is not ReviewDecision.CHANGES_REQUESTED:
            raise ValueError("correction só acompanha decision changes_requested")
        return self


class ReportVersionOut(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: ReportVersion
    status: ReportStatus = Field(description="Revisão por papel sobre a versão ATUAL da série")
    is_current: bool
    current_version_id: UUID
    reporting_period_id: UUID
    content_hash: str = Field(description="SHA-256 do JSON canônico do draft")
    evidence_event_id: UUID = Field(description="Evento do ledger que registrou a versão")


class ReviewOut(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    review: ReportReview
    evidence_event_id: UUID
    new_version: ReportVersion | None = None


class VersionConflictOut(BaseModel):
    """409: a revisão apontou uma versão que não é a atual; nada foi gravado."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    detail: str
    requested_version_id: UUID
    current_version_id: UUID


class ReportReviewFlag(BaseModel):
    """Versão atual que voltou a precisar de revisão porque uma evidência citada foi corrigida."""

    model_config = ConfigDict(frozen=True)

    report_version_id: UUID
    researcher_id: UUID
    superseded_event_id: UUID = Field(description="Evidência original, substituída")
    cause_event_id: UUID = Field(description="Evento de correção que causou a revisão")
    marked_at: datetime
