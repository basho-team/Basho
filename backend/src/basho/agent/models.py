"""Modelos ORM do módulo agent. Privados ao módulo (ADR-0001)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKeyConstraint, Text, UniqueConstraint, func
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
