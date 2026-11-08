"""Modelo ORM do audit log. Privado ao módulo audit (ADR-0001)."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Integer, Text, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class AuditLogRow(Base):
    __tablename__ = "audit_log"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    event_type: Mapped[str] = mapped_column(Text)
    actor_type: Mapped[str] = mapped_column(Text)
    actor_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    run_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    tool: Mapped[str] = mapped_column(Text)
    level: Mapped[str | None] = mapped_column(Text)
    decision: Mapped[str] = mapped_column(Text)
    outcome: Mapped[str] = mapped_column(Text)
    reason_code: Mapped[str | None] = mapped_column(Text)
    input_keys: Mapped[list[str]] = mapped_column(ARRAY(Text))
    input_size_bytes: Mapped[int] = mapped_column(Integer)
    approval_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
