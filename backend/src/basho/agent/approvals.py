"""Aprovação humana de tools `external` (ADR-0005).

Append-only: o pedido é imutável e a decisão é uma linha separada, no máximo uma por pedido
(`UNIQUE(approval_id)`). O estado é derivado: sem decisão → `pending`. Aprovar **não** executa a
tool; a execução do pedido aprovado é feita depois pelo worker (#10), fora do fluxo do Maker.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol, Self
from uuid import UUID, uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import insert, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from basho.agent.models import ToolApprovalDecisionRow, ToolApprovalRequestRow
from basho.agent.tools import PermissionLevel
from basho.audit import (
    ActorType,
    AuditDecision,
    AuditEventType,
    AuditOutcome,
    AuditSink,
    InputSummary,
    NewAuditEntry,
)


class ApprovalDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


class ApprovalState(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ApprovalError(RuntimeError):
    """Erro base do fluxo de aprovação."""


class ApprovalNotFoundError(ApprovalError, LookupError):
    """Pedido inexistente neste tenant."""


class ApprovalAlreadyDecidedError(ApprovalError):
    """O pedido já tem decisão; decisões não são alteradas."""


class NewApprovalRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    tenant_id: UUID
    run_id: UUID
    tool: str = Field(pattern=r"^[a-z][a-z0-9_]{2,63}$")
    level: PermissionLevel
    arguments: dict[str, Any] = Field(description="Entrada proposta, para o humano revisar")

    @model_validator(mode="after")
    def _only_external(self) -> Self:
        if self.level is not PermissionLevel.EXTERNAL:
            raise ValueError("só tools external passam por aprovação")
        return self


class ApprovalRequest(NewApprovalRequest):
    id: UUID
    created_at: AwareDatetime


class ApprovalView(BaseModel):
    """Pedido + decisão (se houver)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    request: ApprovalRequest
    state: ApprovalState
    decided_by: UUID | None = None
    decided_at: AwareDatetime | None = None


class ApprovalStore(Protocol):
    async def create(self, request: NewApprovalRequest) -> ApprovalRequest: ...

    async def get(self, tenant_id: UUID, approval_id: UUID) -> ApprovalView: ...

    async def decide(
        self, tenant_id: UUID, approval_id: UUID, decision: ApprovalDecision, decided_by: UUID
    ) -> ApprovalView: ...


class InMemoryApprovalStore:
    """Store em memória (testes e modo simulado), com as mesmas regras do Postgres."""

    def __init__(self) -> None:
        self._requests: dict[UUID, ApprovalRequest] = {}
        self._decisions: dict[UUID, tuple[ApprovalDecision, UUID, datetime]] = {}

    async def create(self, request: NewApprovalRequest) -> ApprovalRequest:
        saved = ApprovalRequest(**request.model_dump(), id=uuid4(), created_at=datetime.now(UTC))
        self._requests[saved.id] = saved
        return saved

    async def get(self, tenant_id: UUID, approval_id: UUID) -> ApprovalView:
        request = self._requests.get(approval_id)
        if request is None or request.tenant_id != tenant_id:
            raise ApprovalNotFoundError("pedido de aprovação não encontrado neste tenant")
        decision = self._decisions.get(approval_id)
        if decision is None:
            return ApprovalView(request=request, state=ApprovalState.PENDING)
        value, decided_by, decided_at = decision
        return ApprovalView(
            request=request,
            state=ApprovalState(value.value),
            decided_by=decided_by,
            decided_at=decided_at,
        )

    async def decide(
        self, tenant_id: UUID, approval_id: UUID, decision: ApprovalDecision, decided_by: UUID
    ) -> ApprovalView:
        current = await self.get(tenant_id, approval_id)
        if current.state is not ApprovalState.PENDING:
            raise ApprovalAlreadyDecidedError("pedido já decidido")
        self._decisions[approval_id] = (decision, decided_by, datetime.now(UTC))
        return await self.get(tenant_id, approval_id)


def _request_of(row: ToolApprovalRequestRow) -> ApprovalRequest:
    return ApprovalRequest.model_validate(
        {
            "id": row.id,
            "tenant_id": row.tenant_id,
            "run_id": row.run_id,
            "tool": row.tool,
            "level": row.level,
            "arguments": row.arguments,
            "created_at": row.created_at,
        }
    )


class PostgresApprovalStore:
    """Store em Postgres. A transação pertence ao chamador (``tenant_session``)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _require_session_tenant(self, tenant_id: UUID) -> None:
        result = await self._session.execute(text("SELECT current_setting('app.tenant_id', true)"))
        if result.scalar_one_or_none() != str(tenant_id):
            raise ApprovalError("tenant da sessão ausente ou diferente do informado")

    async def create(self, request: NewApprovalRequest) -> ApprovalRequest:
        await self._require_session_tenant(request.tenant_id)
        values = {
            "id": uuid4(),
            "tenant_id": request.tenant_id,
            "run_id": request.run_id,
            "tool": request.tool,
            "level": request.level.value,
            "arguments": request.arguments,
        }
        statement = (
            insert(ToolApprovalRequestRow).values(**values).returning(ToolApprovalRequestRow)
        )
        return _request_of((await self._session.execute(statement)).scalar_one())

    async def get(self, tenant_id: UUID, approval_id: UUID) -> ApprovalView:
        await self._require_session_tenant(tenant_id)
        statement = (
            select(ToolApprovalRequestRow, ToolApprovalDecisionRow)
            .outerjoin(
                ToolApprovalDecisionRow,
                ToolApprovalDecisionRow.approval_id == ToolApprovalRequestRow.id,
            )
            .where(
                ToolApprovalRequestRow.tenant_id == tenant_id,
                ToolApprovalRequestRow.id == approval_id,
            )
        )
        found = (await self._session.execute(statement)).one_or_none()
        if found is None:
            raise ApprovalNotFoundError("pedido de aprovação não encontrado neste tenant")
        request_row, decision_row = found
        request = _request_of(request_row)
        if decision_row is None:
            return ApprovalView(request=request, state=ApprovalState.PENDING)
        return ApprovalView(
            request=request,
            state=ApprovalState(decision_row.decision),
            decided_by=decision_row.decided_by,
            decided_at=decision_row.created_at,
        )

    async def decide(
        self, tenant_id: UUID, approval_id: UUID, decision: ApprovalDecision, decided_by: UUID
    ) -> ApprovalView:
        current = await self.get(tenant_id, approval_id)
        if current.state is not ApprovalState.PENDING:
            raise ApprovalAlreadyDecidedError("pedido já decidido")
        statement = insert(ToolApprovalDecisionRow).values(
            id=uuid4(),
            tenant_id=tenant_id,
            approval_id=approval_id,
            decision=decision.value,
            decided_by=decided_by,
        )
        try:
            async with self._session.begin_nested():
                await self._session.execute(statement)
        except IntegrityError:  # corrida: outra decisão entrou entre o get e o insert
            raise ApprovalAlreadyDecidedError("pedido já decidido") from None
        return await self.get(tenant_id, approval_id)


async def decide_approval(
    store: ApprovalStore,
    audit: AuditSink,
    *,
    tenant_id: UUID,
    approval_id: UUID,
    decision: ApprovalDecision,
    decided_by: UUID,
) -> ApprovalView:
    """Registra a decisão humana e o audit correspondente. Não executa a tool."""
    view = await store.decide(tenant_id, approval_id, decision, decided_by)
    await audit.record(
        NewAuditEntry(
            tenant_id=tenant_id,
            event_type=AuditEventType.APPROVAL_DECIDED,
            actor_type=ActorType.USER,
            actor_id=decided_by,
            run_id=view.request.run_id,
            tool=view.request.tool,
            level=view.request.level,
            decision=AuditDecision(decision.value),
            outcome=AuditOutcome.NOT_EXECUTED,
            input_summary=InputSummary.of(view.request.arguments),
            approval_id=approval_id,
        )
    )
    return view
