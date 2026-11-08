"""Execução do agente: `AgentRun` e máquina de estados (ADR-0009, proposta).

Fronteira IA/código: transições de estado, tentativas e idempotência são decididas por código,
nunca pelo modelo. O estado de execução é separado do estado de negócio (revisão, status de
afirmação, artefato).
"""

from __future__ import annotations

from enum import StrEnum
from types import MappingProxyType
from typing import Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from basho.agent.tasks import PROMPT_VERSION_PATTERN, TaskKind

DEFAULT_MAX_ATTEMPTS = 3
IDEMPOTENCY_KEY_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9:._-]{7,127}$"


class RunStatus(StrEnum):
    """Estado de **execução** de um job do agente.

    Nunca é estado de conformidade nem de revisão: `completed` significa só que o job terminou,
    não que o artefato foi aprovado. `awaiting_input` encerra o job; a resposta humana cria um
    novo `AgentRun` com o mesmo `correlation_id` e `parent_run_id` apontando para este.
    """

    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_INPUT = "awaiting_input"
    COMPLETED = "completed"
    FAILED = "failed"


ALLOWED_TRANSITIONS: MappingProxyType[RunStatus, frozenset[RunStatus]] = MappingProxyType(
    {
        RunStatus.QUEUED: frozenset({RunStatus.RUNNING, RunStatus.FAILED}),
        RunStatus.RUNNING: frozenset(
            {
                RunStatus.QUEUED,  # retry após erro transitório
                RunStatus.AWAITING_INPUT,
                RunStatus.COMPLETED,
                RunStatus.FAILED,
            }
        ),
        RunStatus.AWAITING_INPUT: frozenset(),
        RunStatus.COMPLETED: frozenset(),
        RunStatus.FAILED: frozenset(),
    }
)
"""Transições permitidas. `awaiting_input`, `completed` e `failed` são terminais para o run."""


def can_transition(current: RunStatus, target: RunStatus) -> bool:
    return target in ALLOWED_TRANSITIONS[current]


class RunError(BaseModel):
    """Erro resumido de execução. Sem segredos, PII ou corpo de resposta de provedor."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str = Field(pattern=r"^[a-z][a-z0-9_]{2,63}$", description="Ex.: provider_timeout")
    message: str = Field(min_length=1, max_length=500)
    retryable: bool


class AgentRun(BaseModel):
    """Um job do agente para um perfil de tarefa."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    tenant_id: UUID
    task_kind: TaskKind
    prompt_version: str = Field(pattern=PROMPT_VERSION_PATTERN)
    status: RunStatus
    correlation_id: UUID = Field(description="Compartilhado pelos runs de uma mesma tarefa")
    parent_run_id: UUID | None = None
    idempotency_key: str = Field(pattern=IDEMPOTENCY_KEY_PATTERN)
    attempts: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=DEFAULT_MAX_ATTEMPTS, ge=1)
    created_at: AwareDatetime
    updated_at: AwareDatetime
    error: RunError | None = None

    @model_validator(mode="after")
    def _invariants(self) -> Self:
        problems: list[str] = []
        if self.attempts > self.max_attempts:
            problems.append("attempts não pode exceder max_attempts")
        if self.updated_at < self.created_at:
            problems.append("updated_at não pode ser anterior a created_at")
        if self.parent_run_id == self.id:
            problems.append("parent_run_id não pode ser o próprio run")
        if self.status is RunStatus.RUNNING and self.attempts < 1:
            problems.append("run em execução precisa ter ao menos uma tentativa")
        if self.status is RunStatus.FAILED and self.error is None:
            problems.append("run failed exige error")
        if self.status is RunStatus.COMPLETED and self.error is not None:
            problems.append("run completed não pode ter error")
        if problems:
            raise ValueError("; ".join(problems))
        return self
