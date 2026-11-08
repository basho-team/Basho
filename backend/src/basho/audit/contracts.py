"""Contratos do audit log (ADR-0005, ADR-0006).

O audit é registro operacional imutável de cada ação de agente ou humano. **Não** é evidência
(não vai para o ledger, ADR-0003) e nunca guarda PII, segredos ou o conteúdo da entrada: só os
nomes dos campos e o tamanho da entrada serializada.
"""

from __future__ import annotations

import json
import re
from collections.abc import Collection, Mapping
from enum import StrEnum
from typing import Any, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from basho.agent.tools import PermissionLevel

CODE_PATTERN = r"^[a-z][a-z0-9_]{2,63}$"
"""Nomes de tool, códigos de motivo e chaves de entrada: identificadores, nunca texto livre."""

_CODE_RE = re.compile(CODE_PATTERN)

MAX_INPUT_KEYS = 32
INVALID_KEY_PLACEHOLDER = "invalid_key"


class ActorType(StrEnum):
    AGENT = "agent"
    USER = "user"
    SYSTEM = "system"


class AuditEventType(StrEnum):
    TOOL_CALL = "tool_call"
    APPROVAL_DECIDED = "approval_decided"


class AuditDecision(StrEnum):
    """Decisão da policy (`tool_call`) ou do humano (`approval_decided`)."""

    ALLOWED = "allowed"
    DENIED = "denied"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"


class AuditOutcome(StrEnum):
    OK = "ok"
    ERROR = "error"
    NOT_EXECUTED = "not_executed"


_DECISIONS_BY_EVENT: Mapping[AuditEventType, frozenset[AuditDecision]] = {
    AuditEventType.TOOL_CALL: frozenset(
        {AuditDecision.ALLOWED, AuditDecision.DENIED, AuditDecision.PENDING_APPROVAL}
    ),
    AuditEventType.APPROVAL_DECIDED: frozenset({AuditDecision.APPROVED, AuditDecision.REJECTED}),
}


class InputSummary(BaseModel):
    """Resumo da entrada **sem valores**: chaves de primeiro nível e tamanho em bytes."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    keys: tuple[str, ...] = Field(max_length=MAX_INPUT_KEYS)
    size_bytes: int = Field(ge=0)

    @classmethod
    def of(
        cls, arguments: Mapping[str, Any], *, allowed_keys: Collection[str] | None = None
    ) -> InputSummary:
        """Resume `arguments` sem nunca falhar (a chamada não pode ficar sem audit).

        Chave fora de `CODE_PATTERN` ou, se `allowed_keys` for dado, fora do schema da tool vira
        `invalid_key` (o nome pode carregar PII). Entrada não serializável → `size_bytes = 0`.
        """

        def safe(key: object) -> str:
            if not isinstance(key, str) or not _CODE_RE.fullmatch(key):
                return INVALID_KEY_PLACEHOLDER
            if allowed_keys is not None and key not in allowed_keys:
                return INVALID_KEY_PLACEHOLDER
            return key

        keys = sorted({safe(key) for key in arguments})[:MAX_INPUT_KEYS]
        try:
            serialized = json.dumps(arguments, sort_keys=True, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            return cls(keys=tuple(keys), size_bytes=0)
        return cls(keys=tuple(keys), size_bytes=len(serialized.encode("utf-8")))


class NewAuditEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    tenant_id: UUID
    event_type: AuditEventType
    actor_type: ActorType
    actor_id: UUID | None = Field(default=None, description="Id opaco do humano; nunca nome/e-mail")
    run_id: UUID | None = None
    tool: str = Field(pattern=CODE_PATTERN)
    level: PermissionLevel | None = Field(
        default=None, description="None só quando a tool pedida não existe no registro"
    )
    decision: AuditDecision
    outcome: AuditOutcome
    reason_code: str | None = Field(default=None, pattern=CODE_PATTERN)
    input_summary: InputSummary
    approval_id: UUID | None = None

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.decision not in _DECISIONS_BY_EVENT[self.event_type]:
            msg = f"decisão {self.decision.value} inválida para {self.event_type.value}"
            raise ValueError(msg)
        executed = self.outcome is not AuditOutcome.NOT_EXECUTED
        if executed and self.decision is not AuditDecision.ALLOWED:
            raise ValueError("só chamada permitida pode ter sido executada")
        if self.decision is AuditDecision.PENDING_APPROVAL and self.approval_id is None:
            raise ValueError("pending_approval exige approval_id")
        if self.level is None and self.decision is not AuditDecision.DENIED:
            raise ValueError("level ausente só em chamada negada de tool desconhecida")
        if self.event_type is AuditEventType.TOOL_CALL and self.run_id is None:
            raise ValueError("chamada de tool exige run_id")
        return self


class AuditEntry(NewAuditEntry):
    id: UUID
    created_at: AwareDatetime
