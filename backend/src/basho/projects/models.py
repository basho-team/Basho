"""Modelos ORM de projetos, atividades, pendências e aprovações (#5). Privados ao módulo."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

_UUID = PG_UUID(as_uuid=True)


class Base(DeclarativeBase):
    pass


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class ProjectRow(Base):
    __tablename__ = "projects"

    id: Mapped[UUID] = mapped_column(_UUID, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(_UUID)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = _created_at()


class ActivityRow(Base):
    __tablename__ = "activities"

    id: Mapped[UUID] = mapped_column(_UUID, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(_UUID)
    project_id: Mapped[UUID] = mapped_column(_UUID)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = _created_at()


class PendingItemRow(Base):
    __tablename__ = "pending_items"

    id: Mapped[UUID] = mapped_column(_UUID, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(_UUID)
    project_id: Mapped[UUID] = mapped_column(_UUID)
    activity_id: Mapped[UUID | None] = mapped_column(_UUID)
    kind: Mapped[str] = mapped_column(Text)
    source_key: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    question: Mapped[str] = mapped_column(Text)
    assignee_role: Mapped[str] = mapped_column(Text)
    artifact_event_id: Mapped[UUID] = mapped_column(_UUID)
    verification_event_id: Mapped[UUID] = mapped_column(_UUID)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = _created_at()


class PendingAnswerRow(Base):
    __tablename__ = "pending_answers"

    id: Mapped[UUID] = mapped_column(_UUID, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(_UUID)
    pending_item_id: Mapped[UUID] = mapped_column(_UUID)
    answer: Mapped[str] = mapped_column(Text)
    corrected_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    answered_by: Mapped[UUID] = mapped_column(_UUID)
    answered_role: Mapped[str] = mapped_column(Text)
    correction_event_id: Mapped[UUID] = mapped_column(_UUID)
    created_at: Mapped[datetime] = _created_at()


class ArtifactApprovalRow(Base):
    __tablename__ = "artifact_approvals"

    id: Mapped[UUID] = mapped_column(_UUID, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(_UUID)
    project_id: Mapped[UUID] = mapped_column(_UUID)
    artifact_event_id: Mapped[UUID] = mapped_column(_UUID)
    decision: Mapped[str] = mapped_column(Text)
    comment: Mapped[str | None] = mapped_column(Text)
    approver_id: Mapped[UUID] = mapped_column(_UUID)
    evidence_event_id: Mapped[UUID] = mapped_column(_UUID)
    created_at: Mapped[datetime] = _created_at()
