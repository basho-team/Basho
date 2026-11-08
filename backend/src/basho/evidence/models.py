"""Modelo ORM do ledger. Privado ao módulo evidence (ADR-0001)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CHAR, Boolean, DateTime, ForeignKeyConstraint, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from basho.evidence.contracts import SHA256_HEX_LENGTH


class Base(DeclarativeBase):
    pass


class EvidenceEventRow(Base):
    __tablename__ = "evidence_events"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_evidence_events_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "supersedes"],
            ["evidence_events.tenant_id", "evidence_events.id"],
            name="fk_evidence_events_supersedes_same_tenant",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    project_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    kind: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)
    source_ref: Mapped[str | None] = mapped_column(Text)
    actor: Mapped[dict[str, Any]] = mapped_column(JSONB)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    content_hash: Mapped[str] = mapped_column(CHAR(SHA256_HEX_LENGTH))
    supersedes: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
