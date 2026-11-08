"""Schemas HTTP do MVP (pendências, correção, aprovação, dossiê).

O OpenAPI gerado pelo FastAPI a partir destes modelos é o contrato do frontend (ADR-0002).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from basho.agent.verifier import VerificationResult
from basho.evidence.contracts import ArtifactStatus, EvidenceEvent


class PendingKind(StrEnum):
    MISSING_JUSTIFICATION = "missing_justification"
    MISSING_ACTIVITY_RECORD = "missing_activity_record"
    CHECKER_DISAGREEMENT = "checker_disagreement"
    APPROVAL_REQUIRED = "approval_required"
    TOOL_FAILURE = "tool_failure"
    NEEDS_REVIEW = "needs_review"


class PendingItemOut(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    project_id: UUID
    activity_id: UUID | None
    kind: PendingKind
    title: str
    question: str
    assignee_role: str
    artifact_id: UUID | None
    artifact_status: ArtifactStatus | None
    created_at: datetime
    resolved: bool


class CorrectionIn(BaseModel):
    """Correção humana: gera USER_CORRECTION com `supersedes` e reabre dependentes."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    target_event_id: UUID
    corrected_payload: dict[str, Any]
    reason: str = Field(min_length=5)


class ConfirmationIn(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    answer: str = Field(min_length=1, description="Resposta à pendência")


class ApprovalDecision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"


class ApprovalIn(BaseModel):
    """Ação FORMAL: só via endpoint humano autenticado (ADR-0005)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    decision: ApprovalDecision
    comment: str | None = None


class AgentRunMetrics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: UUID
    model: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    latency_ms: int = Field(ge=0)
    cost_usd: float = Field(ge=0)


class DossierEntryOut(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_id: UUID
    activity_id: UUID
    title: str
    status: ArtifactStatus
    content: dict[str, Any]
    evidence: tuple[EvidenceEvent, ...]
    verifications: tuple[VerificationResult, ...]
    history: tuple[EvidenceEvent, ...]
    runs: tuple[AgentRunMetrics, ...]
