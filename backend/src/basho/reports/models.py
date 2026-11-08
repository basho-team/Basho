"""Modelos ORM da persistência de reports (#39). Privados ao módulo (ADR-0001).

Espelham os tipos de domínio `ReportVersion` e `ReportReview` (`basho.reports.versions`).
"""

from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CHAR, Boolean, Date, DateTime, Integer, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from basho.evidence.contracts import SHA256_HEX_LENGTH

_UUID = PG_UUID(as_uuid=True)


class Base(DeclarativeBase):
    pass


class ReportingPeriodRow(Base):
    __tablename__ = "reporting_periods"

    id: Mapped[UUID] = mapped_column(_UUID, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(_UUID)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    timezone: Mapped[str] = mapped_column(Text)
    periodicity: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReportVersionRow(Base):
    __tablename__ = "report_versions"

    id: Mapped[UUID] = mapped_column(_UUID, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(_UUID)
    project_id: Mapped[UUID] = mapped_column(_UUID)
    researcher_id: Mapped[UUID] = mapped_column(_UUID)
    reporting_period_id: Mapped[UUID] = mapped_column(_UUID)
    number: Mapped[int] = mapped_column(Integer)
    supersedes_id: Mapped[UUID | None] = mapped_column(_UUID)
    draft: Mapped[dict[str, Any]] = mapped_column(JSONB)
    claim_ids: Mapped[list[UUID]] = mapped_column(ARRAY(_UUID))
    experiment_ids: Mapped[list[UUID]] = mapped_column(ARRAY(_UUID))
    missing_ids: Mapped[list[UUID]] = mapped_column(ARRAY(_UUID))
    # none_as_null: v1 grava SQL NULL (não JSON null), exigido por ck_report_versions_lineage
    change: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    content_hash: Mapped[str] = mapped_column(CHAR(SHA256_HEX_LENGTH))
    evidence_event_id: Mapped[UUID] = mapped_column(_UUID)
    cited_evidence_ids: Mapped[list[UUID]] = mapped_column(ARRAY(_UUID))
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ReportReviewRow(Base):
    __tablename__ = "report_reviews"

    id: Mapped[UUID] = mapped_column(_UUID, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(_UUID)
    report_version_id: Mapped[UUID] = mapped_column(_UUID)
    reviewer_id: Mapped[UUID] = mapped_column(_UUID)
    reviewer_role: Mapped[str] = mapped_column(Text)
    decision: Mapped[str] = mapped_column(Text)
    comment: Mapped[str | None] = mapped_column(Text)
    new_version_id: Mapped[UUID | None] = mapped_column(_UUID)
    evidence_event_id: Mapped[UUID] = mapped_column(_UUID)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
