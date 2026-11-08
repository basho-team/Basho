"""Policy de execução de tools (ADR-0005, ADR-0006).

Toda chamada do Maker passa por `ToolPolicy.execute`, que decide **em código** — a cada
chamada, sem confiar só no perfil — se a tool roda, fica pendente de aprovação ou é negada, e
grava uma linha de audit em todos os casos. Conteúdo externo devolvido pela tool é envelopado
como dado não confiável antes de chegar ao Maker.
"""

from __future__ import annotations

import asyncio
import html
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from uuid import UUID

from basho.agent.approvals import ApprovalStore, NewApprovalRequest
from basho.agent.registry import ToolRegistry
from basho.agent.tasks import TaskProfile
from basho.agent.tools import (
    AGENT_ALLOWED_LEVELS,
    PermissionLevel,
    Tool,
    ToolCallStatus,
    ToolResult,
)
from basho.audit import (
    CODE_PATTERN,
    ActorType,
    AuditDecision,
    AuditEventType,
    AuditOutcome,
    AuditSink,
    InputSummary,
    NewAuditEntry,
)
from basho.logging import get_logger

DEFAULT_TOOL_TIMEOUT_SECONDS = 30.0
MAX_APPROVAL_ARGUMENTS_BYTES = 16_384
"""Teto da entrada guardada num pedido de aprovação (o humano precisa conseguir revisá-la)."""
_CODE_RE = re.compile(CODE_PATTERN)
UNKNOWN_TOOL_AUDIT_NAME = "unknown_tool"
UNTRUSTED_OPEN = '<untrusted_data tool="{tool}">'
UNTRUSTED_CLOSE = "</untrusted_data>"

_log = get_logger(__name__)


class DenialReason(StrEnum):
    UNKNOWN_TOOL = "unknown_tool"
    LEVEL_NOT_ALLOWED = "level_not_allowed"
    NOT_IN_PROFILE = "not_in_profile"
    ARGUMENTS_TOO_LARGE = "arguments_too_large"


class FailureReason(StrEnum):
    CANCELLED = "cancelled"
    TOOL_TIMEOUT = "tool_timeout"
    TOOL_FAILED = "tool_failed"
    TOOL_ERROR = "tool_error"
    INVALID_RESULT = "invalid_result"


@dataclass(frozen=True, slots=True)
class ToolCallContext:
    """Quem está chamando: tenant, run e perfil da tarefa."""

    tenant_id: UUID
    run_id: UUID
    profile: TaskProfile


def envelope_untrusted(tool: str, content: str) -> str:
    """Envelopa texto externo como dado (ADR-0006).

    `<`, `>` e `&` são escapados, então o conteúdo não consegue fechar o envelope nem abrir
    marcações próprias. O Maker trata tudo dentro do envelope como dado, nunca instrução.
    """
    escaped = html.escape(content, quote=False)
    return f"{UNTRUSTED_OPEN.format(tool=tool)}\n{escaped}\n{UNTRUSTED_CLOSE}"


class ToolPolicy:
    def __init__(
        self,
        registry: ToolRegistry,
        audit: AuditSink,
        approvals: ApprovalStore,
        *,
        external_requires_approval: bool = True,
        timeout_seconds: float = DEFAULT_TOOL_TIMEOUT_SECONDS,
    ) -> None:
        """`external_requires_approval` é a configuração do tenant (padrão: requer)."""
        self._registry = registry
        self._audit = audit
        self._approvals = approvals
        self._external_requires_approval = external_requires_approval
        self._timeout_seconds = timeout_seconds

    async def execute(
        self, context: ToolCallContext, tool_name: str, arguments: Mapping[str, Any]
    ) -> ToolResult:
        entry = self._registry.get(tool_name)
        if entry is None:
            summary = InputSummary.of(arguments, allowed_keys=())
            return await self._deny(context, tool_name, None, summary, DenialReason.UNKNOWN_TOOL)
        spec = entry.spec  # spec congelada no registro, nunca `entry.tool.spec`
        summary = InputSummary.of(arguments, allowed_keys=_schema_keys(spec.input_schema))
        if spec.level not in AGENT_ALLOWED_LEVELS:
            return await self._deny(
                context, spec.name, spec.level, summary, DenialReason.LEVEL_NOT_ALLOWED
            )
        if spec.name not in context.profile.allowed_tools:
            return await self._deny(
                context, spec.name, spec.level, summary, DenialReason.NOT_IN_PROFILE
            )
        if spec.level is PermissionLevel.EXTERNAL and (
            spec.requires_approval or self._external_requires_approval
        ):
            if summary.size_bytes > MAX_APPROVAL_ARGUMENTS_BYTES:
                return await self._deny(
                    context, spec.name, spec.level, summary, DenialReason.ARGUMENTS_TOO_LARGE
                )
            return await self._request_approval(context, spec.name, arguments, summary)

        try:
            result, failure = await self._run(entry.tool, spec.name, context, dict(arguments))
        except asyncio.CancelledError:
            # A tool pode já ter tido efeito: a chamada não pode ficar sem audit.
            await self._record(
                context,
                spec.name,
                spec.level,
                AuditDecision.ALLOWED,
                AuditOutcome.ERROR,
                summary,
                reason=FailureReason.CANCELLED,
            )
            raise
        outcome = AuditOutcome.OK if result.status is ToolCallStatus.OK else AuditOutcome.ERROR
        await self._record(
            context,
            spec.name,
            spec.level,
            AuditDecision.ALLOWED,
            outcome,
            summary,
            reason=failure,
        )
        return result

    async def _run(
        self, tool: Tool, name: str, context: ToolCallContext, arguments: dict[str, Any]
    ) -> tuple[ToolResult, str | None]:
        try:
            async with asyncio.timeout(self._timeout_seconds):
                raw = await tool.run(str(context.tenant_id), arguments)
        except TimeoutError:
            return _error(name, FailureReason.TOOL_TIMEOUT), FailureReason.TOOL_TIMEOUT
        except Exception as exc:  # a falha da tool não derruba o run; detalhe só no log
            _log.warning(
                "tool_failed", tool=name, run_id=str(context.run_id), error=type(exc).__name__
            )
            return _error(name, FailureReason.TOOL_FAILED), FailureReason.TOOL_FAILED
        if (
            not isinstance(raw, ToolResult)
            or raw.tool != name
            or raw.status
            not in {
                ToolCallStatus.OK,
                ToolCallStatus.ERROR,
            }
        ):
            return _error(name, FailureReason.INVALID_RESULT), FailureReason.INVALID_RESULT
        normalized: dict[str, Any] = {}
        if raw.untrusted_data is not None:
            normalized["untrusted_data"] = envelope_untrusted(name, raw.untrusted_data)
        if raw.error is not None and not _CODE_RE.fullmatch(raw.error):
            # `error` chega ao Maker fora do envelope: só códigos, nunca texto do provedor.
            normalized["error"] = FailureReason.TOOL_ERROR.value
        if normalized:
            raw = ToolResult.model_validate(raw.model_dump() | normalized)
        failure = FailureReason.TOOL_ERROR if raw.status is ToolCallStatus.ERROR else None
        return raw, failure

    async def _request_approval(
        self,
        context: ToolCallContext,
        name: str,
        arguments: Mapping[str, Any],
        summary: InputSummary,
    ) -> ToolResult:
        request = await self._approvals.create(
            NewApprovalRequest(
                tenant_id=context.tenant_id,
                run_id=context.run_id,
                tool=name,
                level=PermissionLevel.EXTERNAL,
                arguments=dict(arguments),
            )
        )
        await self._record(
            context,
            name,
            PermissionLevel.EXTERNAL,
            AuditDecision.PENDING_APPROVAL,
            AuditOutcome.NOT_EXECUTED,
            summary,
            approval_id=request.id,
        )
        return ToolResult(
            tool=name, status=ToolCallStatus.PENDING_APPROVAL, approval_id=str(request.id)
        )

    async def _deny(
        self,
        context: ToolCallContext,
        name: str,
        level: PermissionLevel | None,
        summary: InputSummary,
        reason: DenialReason,
    ) -> ToolResult:
        # Nome desconhecido vem do modelo: não vai para o audit (pode ser texto arbitrário).
        audited_name = UNKNOWN_TOOL_AUDIT_NAME if reason is DenialReason.UNKNOWN_TOOL else name
        await self._record(
            context,
            audited_name,
            level,
            AuditDecision.DENIED,
            AuditOutcome.NOT_EXECUTED,
            summary,
            reason=reason,
        )
        return ToolResult(tool=audited_name, status=ToolCallStatus.DENIED, error=reason.value)

    async def _record(
        self,
        context: ToolCallContext,
        name: str,
        level: PermissionLevel | None,
        decision: AuditDecision,
        outcome: AuditOutcome,
        summary: InputSummary,
        *,
        reason: str | None = None,
        approval_id: UUID | None = None,
    ) -> None:
        await self._audit.record(
            NewAuditEntry(
                tenant_id=context.tenant_id,
                event_type=AuditEventType.TOOL_CALL,
                actor_type=ActorType.AGENT,
                run_id=context.run_id,
                tool=name,
                level=level,
                decision=decision,
                outcome=outcome,
                reason_code=reason,
                input_summary=summary,
                approval_id=approval_id,
            )
        )


def _schema_keys(input_schema: Mapping[str, Any]) -> frozenset[str]:
    properties = input_schema.get("properties")
    return frozenset(properties) if isinstance(properties, Mapping) else frozenset()


def _error(tool: str, reason: FailureReason) -> ToolResult:
    return ToolResult(tool=tool, status=ToolCallStatus.ERROR, error=reason.value)
