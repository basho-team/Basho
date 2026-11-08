"""Modelos ORM do módulo agent. Privados ao módulo (ADR-0001)."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ToolApprovalRequestRow(Base):
    __tablename__ = "tool_approval_requests"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_tool_approval_requests_tenant_id"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    tool: Mapped[str] = mapped_column(Text)
    level: Mapped[str] = mapped_column(Text)
    arguments: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ToolApprovalDecisionRow(Base):
    __tablename__ = "tool_approval_decisions"
    __table_args__ = (
        UniqueConstraint("approval_id", name="uq_tool_approval_decisions_approval_id"),
        ForeignKeyConstraint(
            ["tenant_id", "approval_id"],
            ["tool_approval_requests.tenant_id", "tool_approval_requests.id"],
            name="fk_tool_approval_decisions_request_same_tenant",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    approval_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    decision: Mapped[str] = mapped_column(Text)
    decided_by: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AgentRunRow(Base):
    """Run do agente e item da fila (migração 0006). Só o worker atualiza colunas de execução."""

    __tablename__ = "agent_runs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_agent_runs_tenant_id"),
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_agent_runs_idempotency"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    project_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    task_kind: Mapped[str] = mapped_column(Text)
    prompt_version: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    correlation_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    parent_run_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    idempotency_key: Mapped[str] = mapped_column(Text)
    dedupe_key: Mapped[str] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer)
    max_attempts: Mapped[int] = mapped_column(Integer)
    # none_as_null: `None` vira SQL NULL (não JSON `null`), como os CHECKs esperam.
    error: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    task_input: Mapped[dict[str, Any]] = mapped_column(JSONB)
    requested_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    is_synthetic: Mapped[bool] = mapped_column(Boolean)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    artifact_event_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    verification_event_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    artifact_status: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AgentCallRow(Base):
    """Um `CallRecord` do Maker (append-only): tracing e custo estimado (#23)."""

    __tablename__ = "agent_calls"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    attempt: Mapped[int] = mapped_column(Integer)
    seq: Mapped[int] = mapped_column(Integer)
    model: Mapped[str] = mapped_column(Text)
    prompt_version: Mapped[str] = mapped_column(Text)
    stop_reason: Mapped[str | None] = mapped_column(Text)
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    cache_read_input_tokens: Mapped[int] = mapped_column(Integer)
    cache_creation_input_tokens: Mapped[int] = mapped_column(Integer)
    latency_ms: Mapped[int] = mapped_column(Integer)
    request_id: Mapped[str | None] = mapped_column(Text)
    estimated_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
