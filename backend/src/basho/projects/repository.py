"""Acesso a dados de projetos e pendências: somente INSERT e SELECT (ADR-0003)."""

from typing import Any, TypeVar
from uuid import UUID

from sqlalchemy import insert, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from basho.projects.models import (
    ActivityRow,
    ArtifactApprovalRow,
    Base,
    PendingAnswerRow,
    PendingItemRow,
    ProjectRow,
)

RowT = TypeVar("RowT", bound=Base)


class ProjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def current_tenant_setting(self) -> str | None:
        result = await self._session.execute(text("SELECT current_setting('app.tenant_id', true)"))
        return result.scalar_one_or_none()

    async def lock(self, key: str) -> None:
        """Serializa ações sobre a mesma chave até o fim da transação (sem UPDATE, #21)."""
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": key}
        )

    async def insert(self, model: type[RowT], values: dict[str, Any]) -> RowT:
        statement = insert(model).values(**values).returning(model)
        async with self._session.begin_nested():  # savepoint: a transação externa sobrevive
            result = await self._session.execute(statement)
        return result.scalar_one()

    async def insert_pending_if_absent(self, rows: list[dict[str, Any]]) -> None:
        """Projeção idempotente: `uq_pending_items_source` descarta o que já existe."""
        if rows:
            await self._session.execute(
                pg_insert(PendingItemRow).values(rows).on_conflict_do_nothing()
            )

    async def get_project(self, tenant_id: UUID, project_id: UUID) -> ProjectRow | None:
        statement = select(ProjectRow).where(
            ProjectRow.tenant_id == tenant_id, ProjectRow.id == project_id
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def activities_of(self, tenant_id: UUID, project_id: UUID) -> list[ActivityRow]:
        statement = (
            select(ActivityRow)
            .where(ActivityRow.tenant_id == tenant_id, ActivityRow.project_id == project_id)
            .order_by(ActivityRow.created_at, ActivityRow.id)
        )
        return list((await self._session.execute(statement)).scalars())

    async def pending_of(self, tenant_id: UUID, project_id: UUID) -> list[PendingItemRow]:
        statement = (
            select(PendingItemRow)
            .where(PendingItemRow.tenant_id == tenant_id, PendingItemRow.project_id == project_id)
            .order_by(PendingItemRow.created_at, PendingItemRow.id)
        )
        return list((await self._session.execute(statement)).scalars())

    async def get_pending(self, tenant_id: UUID, pending_id: UUID) -> PendingItemRow | None:
        statement = select(PendingItemRow).where(
            PendingItemRow.tenant_id == tenant_id, PendingItemRow.id == pending_id
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def answers_of(self, tenant_id: UUID, project_id: UUID) -> list[PendingAnswerRow]:
        statement = (
            select(PendingAnswerRow)
            .join(
                PendingItemRow,
                (PendingItemRow.tenant_id == PendingAnswerRow.tenant_id)
                & (PendingItemRow.id == PendingAnswerRow.pending_item_id),
            )
            .where(PendingItemRow.tenant_id == tenant_id, PendingItemRow.project_id == project_id)
        )
        return list((await self._session.execute(statement)).scalars())

    async def approvals_of(self, tenant_id: UUID, project_id: UUID) -> list[ArtifactApprovalRow]:
        statement = select(ArtifactApprovalRow).where(
            ArtifactApprovalRow.tenant_id == tenant_id,
            ArtifactApprovalRow.project_id == project_id,
        )
        return list((await self._session.execute(statement)).scalars())
