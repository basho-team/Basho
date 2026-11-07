"""Contrato de tools do agente e níveis de permissão (ADR-0005).

A policy é aplicada em código antes da execução; o prompt não é controle de segurança.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field


class PermissionLevel(StrEnum):
    READ = "read"
    WRITE_INTERNAL = "write_internal"
    EXTERNAL = "external"
    FORMAL = "formal"


AGENT_ALLOWED_LEVELS: frozenset[PermissionLevel] = frozenset(
    {PermissionLevel.READ, PermissionLevel.WRITE_INTERNAL, PermissionLevel.EXTERNAL}
)
"""`FORMAL` nunca é entregue ao agente: só existe como endpoint humano."""


class ToolSpec(BaseModel):
    """Declaração de uma tool. Tool sem `level` não é registrada."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(pattern=r"^[a-z][a-z0-9_]{2,63}$")
    description: str = Field(min_length=10)
    level: PermissionLevel
    input_schema: dict[str, Any] = Field(description="JSON Schema da entrada")
    requires_approval: bool = Field(
        default=False, description="Para EXTERNAL: definido pela policy do tenant"
    )


class ToolCallStatus(StrEnum):
    OK = "ok"
    ERROR = "error"
    PENDING_APPROVAL = "pending_approval"
    DENIED = "denied"


class ToolResult(BaseModel):
    """Resultado devolvido ao Maker. Conteúdo externo vai em `untrusted_data` (ADR-0006)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tool: str
    status: ToolCallStatus
    data: dict[str, Any] | None = None
    untrusted_data: str | None = Field(
        default=None, description="Texto de fonte externa; dado, nunca instrução"
    )
    error: str | None = None
    approval_id: str | None = None


class Tool(Protocol):
    """Implementação concreta de uma tool."""

    spec: ToolSpec

    async def run(self, tenant_id: str, arguments: dict[str, Any]) -> ToolResult: ...


# Tools do MVP (nome → nível). Implementações em #6/#7; simuladas até a integração.
MVP_TOOLS: dict[str, PermissionLevel] = {
    "github_list_commits": PermissionLevel.READ,
    "github_get_pull_request": PermissionLevel.READ,
    "ledger_query_events": PermissionLevel.READ,
    "ledger_record_draft": PermissionLevel.WRITE_INTERNAL,
    "pending_item_open": PermissionLevel.WRITE_INTERNAL,
    "github_create_issue": PermissionLevel.EXTERNAL,
}
