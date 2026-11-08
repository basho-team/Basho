"""Acesso a dados de reports: somente INSERT e SELECT (ADR-0003)."""

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import insert, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from basho.agent.artifacts import ReportingPeriod
from basho.reports.models import ReportingPeriodRow, ReportReviewRow, ReportVersionRow


class ReportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def current_tenant_setting(self) -> str | None:
        """Valor de ``app.tenant_id`` na transação atual (None se ausente)."""
        result = await self._session.execute(text("SELECT current_setting('app.tenant_id', true)"))
        return result.scalar_one_or_none()

    async def lock_series(self, key: str) -> None:
        """Serializa a série até o fim da transação.

        Advisory lock em vez de ``SELECT ... FOR UPDATE``, que exigiria privilégio UPDATE
        que os roles da app não têm (#21).
        """
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": key}
        )

    async def get_or_create_period(self, tenant_id: UUID, period: ReportingPeriod) -> UUID:
        natural_key = {
            "tenant_id": tenant_id,
            "start_date": period.start,
            "end_date": period.end,
            "timezone": period.timezone,
            "periodicity": period.periodicity.value,
        }
        await self._session.execute(
            pg_insert(ReportingPeriodRow).values(id=uuid4(), **natural_key).on_conflict_do_nothing()
        )
        statement = select(ReportingPeriodRow.id).where(
            *(getattr(ReportingPeriodRow, name) == value for name, value in natural_key.items())
        )
        return (await self._session.execute(statement)).scalar_one()

    async def find_period(self, tenant_id: UUID, period: ReportingPeriod) -> UUID | None:
        """Localiza o período sem criá-lo (leituras não gravam nada)."""
        statement = select(ReportingPeriodRow.id).where(
            ReportingPeriodRow.tenant_id == tenant_id,
            ReportingPeriodRow.start_date == period.start,
            ReportingPeriodRow.end_date == period.end,
            ReportingPeriodRow.timezone == period.timezone,
            ReportingPeriodRow.periodicity == period.periodicity.value,
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def project_versions(
        self, tenant_id: UUID, project_id: UUID, period_id: UUID
    ) -> list[ReportVersionRow]:
        """Todas as versões de todas as séries do projeto no período (pesquisador, número)."""
        statement = (
            select(ReportVersionRow)
            .where(
                ReportVersionRow.tenant_id == tenant_id,
                ReportVersionRow.project_id == project_id,
                ReportVersionRow.reporting_period_id == period_id,
            )
            .order_by(ReportVersionRow.researcher_id, ReportVersionRow.number)
        )
        return list((await self._session.execute(statement)).scalars())

    async def get_version(self, tenant_id: UUID, version_id: UUID) -> ReportVersionRow | None:
        statement = select(ReportVersionRow).where(
            ReportVersionRow.tenant_id == tenant_id, ReportVersionRow.id == version_id
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def series(
        self, tenant_id: UUID, project_id: UUID, researcher_id: UUID, period_id: UUID
    ) -> list[ReportVersionRow]:
        """Todas as versões da série, da v1 à atual."""
        statement = (
            select(ReportVersionRow)
            .where(
                ReportVersionRow.tenant_id == tenant_id,
                ReportVersionRow.project_id == project_id,
                ReportVersionRow.researcher_id == researcher_id,
                ReportVersionRow.reporting_period_id == period_id,
            )
            .order_by(ReportVersionRow.number)
        )
        return list((await self._session.execute(statement)).scalars())

    async def reviews_of(self, tenant_id: UUID, version_ids: list[UUID]) -> list[ReportReviewRow]:
        statement = (
            select(ReportReviewRow)
            .where(
                ReportReviewRow.tenant_id == tenant_id,
                ReportReviewRow.report_version_id.in_(version_ids),
            )
            .order_by(ReportReviewRow.reviewed_at, ReportReviewRow.id)
        )
        return list((await self._session.execute(statement)).scalars())

    async def insert_version(self, values: dict[str, Any]) -> ReportVersionRow:
        statement = insert(ReportVersionRow).values(**values).returning(ReportVersionRow)
        async with self._session.begin_nested():  # savepoint: a transação externa sobrevive
            result = await self._session.execute(statement)
        return result.scalar_one()

    async def insert_review(self, values: dict[str, Any]) -> ReportReviewRow:
        statement = insert(ReportReviewRow).values(**values).returning(ReportReviewRow)
        async with self._session.begin_nested():
            result = await self._session.execute(statement)
        return result.scalar_one()
