"""Schemas HTTP do MVP (projetos, pendências, resposta, aprovação, dossiê) — issue #5.

O OpenAPI gerado pelo FastAPI a partir destes modelos é o contrato do frontend (ADR-0002).
"Artefato" é o evento `activity_record` do Maker no ledger: `artifact_id` = id desse evento.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from basho.agent.verifier import VerificationResult
from basho.evidence.contracts import ArtifactStatus, EvidenceEvent

MAX_ANSWER_LENGTH = 4000
MAX_COMMENT_LENGTH = 2000


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ActivityOut(_Frozen):
    id: UUID
    project_id: UUID
    title: str
    description: str | None
    is_synthetic: bool
    created_at: datetime


class ProjectOut(_Frozen):
    id: UUID
    name: str
    description: str | None
    is_synthetic: bool
    created_at: datetime
    activities: tuple[ActivityOut, ...]
    open_pending: int = Field(ge=0, description="Pendências com status `open`")


class PendingKind(StrEnum):
    MISSING_JUSTIFICATION = "missing_justification"
    MISSING_ACTIVITY_RECORD = "missing_activity_record"
    CHECKER_DISAGREEMENT = "checker_disagreement"
    APPROVAL_REQUIRED = "approval_required"
    TOOL_FAILURE = "tool_failure"
    NEEDS_REVIEW = "needs_review"


class PendingStatus(StrEnum):
    OPEN = "open"
    ANSWERED = "answered"  # resposta humana gravada (USER_CORRECTION)
    RESOLVED = "resolved"  # encerrada por decisão formal sobre o artefato


class PendingItemOut(_Frozen):
    """Pendência aberta a partir de um `verification_result` (`needs_human` ou `verified`)."""

    id: UUID
    project_id: UUID
    activity_id: UUID | None
    kind: PendingKind
    title: str
    question: str = Field(description="Pergunta objetiva; texto do Maker é dado, não instrução")
    assignee_role: str
    artifact_id: UUID | None
    artifact_status: ArtifactStatus | None
    verification_event_id: UUID
    status: PendingStatus
    resolved: bool = Field(description="status != open (compatibilidade)")
    response: str | None
    created_at: datetime


class PendingPageOut(_Frozen):
    items: tuple[PendingItemOut, ...]
    next_offset: int | None = Field(description="Offset da próxima página; null se acabou")


class PendingAnswerIn(_Frozen):
    """Resposta/correção humana: vira `user_correction` com `supersedes` = artefato."""

    answer: str = Field(min_length=1, max_length=MAX_ANSWER_LENGTH)
    corrected_payload: dict[str, Any] | None = Field(
        default=None, description="Campos corrigidos pelo humano (opcional)"
    )


class PendingAnswerOut(_Frozen):
    pending: PendingItemOut
    correction_event_id: UUID


class ApprovalDecision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"


class ApprovalIn(_Frozen):
    """Ação FORMAL: só via endpoint humano, papel `manager` (ADR-0005)."""

    decision: ApprovalDecision
    comment: str | None = Field(default=None, max_length=MAX_COMMENT_LENGTH)


class ApprovalOut(_Frozen):
    artifact_id: UUID
    decision: ApprovalDecision
    status: ArtifactStatus
    approver_id: UUID
    comment: str | None
    evidence_event_id: UUID
    created_at: datetime


class ConflictOut(_Frozen):
    """409: a ação não vale no estado atual (ex.: artefato não `verified`, pendência fechada)."""

    detail: str
    code: str
    current_status: str | None = None


class AgentRunMetrics(_Frozen):
    run_id: UUID
    model: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    latency_ms: int = Field(ge=0)
    cost_usd: float = Field(ge=0)


class DossierEntryOut(_Frozen):
    artifact_id: UUID
    activity_id: UUID | None
    title: str
    status: ArtifactStatus
    content: dict[str, Any] = Field(description="Rascunho do Maker (`draft`)")
    evidence: tuple[EvidenceEvent, ...] = Field(description="Fontes citadas")
    verifications: tuple[VerificationResult, ...]
    history: tuple[EvidenceEvent, ...] = Field(
        description="Artefato, vereditos, correções e decisões, do mais antigo ao mais novo"
    )
    approval: ApprovalOut | None
    run_id: UUID | None
    runs: tuple[AgentRunMetrics, ...] = Field(description="Vazio até existir agent_runs (#10)")


class DossierOut(_Frozen):
    project: ProjectOut
    entries: tuple[DossierEntryOut, ...]
