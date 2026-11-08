"""Acesso a dados do ledger: somente INSERT e SELECT (ADR-0003)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import insert, select, text, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from basho.evidence.models import EvidenceEventRow


class EvidenceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def current_tenant_setting(self) -> str | None:
        """Valor de ``app.tenant_id`` na transação atual (None se ausente)."""
        result = await self._session.execute(text("SELECT current_setting('app.tenant_id', true)"))
        return result.scalar_one_or_none()

    async def insert(self, values: dict[str, Any]) -> EvidenceEventRow:
        """Insere e devolve a linha com ``created_at`` gerado pelo banco."""
        statement = insert(EvidenceEventRow).values(**values).returning(EvidenceEventRow)
        async with self._session.begin_nested():  # savepoint: a transação externa sobrevive
            result = await self._session.execute(statement)
        return result.scalar_one()

    async def get(self, tenant_id: UUID, event_id: UUID) -> EvidenceEventRow | None:
        statement = select(EvidenceEventRow).where(
            EvidenceEventRow.tenant_id == tenant_id, EvidenceEventRow.id == event_id
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def existing_ids(
        self, tenant_id: UUID, project_id: UUID, event_ids: list[UUID]
    ) -> set[UUID]:
        """IDs de ``event_ids`` que existem no ledger do tenant E do projeto (1 query)."""
        statement = select(EvidenceEventRow.id).where(
            EvidenceEventRow.tenant_id == tenant_id,
            EvidenceEventRow.project_id == project_id,
            EvidenceEventRow.id.in_(event_ids),
        )
        return set((await self._session.execute(statement)).scalars())

    async def get_many(
        self, tenant_id: UUID, project_id: UUID, event_ids: list[UUID]
    ) -> list[EvidenceEventRow]:
        """Eventos de ``event_ids`` do tenant E do projeto, do mais antigo ao mais novo."""
        statement = (
            select(EvidenceEventRow)
            .where(
                EvidenceEventRow.tenant_id == tenant_id,
                EvidenceEventRow.project_id == project_id,
                EvidenceEventRow.id.in_(event_ids),
            )
            .order_by(EvidenceEventRow.created_at, EvidenceEventRow.id)
        )
        return list((await self._session.execute(statement)).scalars())

    async def project_of(self, tenant_id: UUID, event_id: UUID) -> UUID | None:
        statement = select(EvidenceEventRow.project_id).where(
            EvidenceEventRow.tenant_id == tenant_id, EvidenceEventRow.id == event_id
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def query(
        self,
        tenant_id: UUID,
        *,
        project_id: UUID | None,
        kinds: list[str] | None,
        limit: int,
        before: tuple[datetime, UUID] | None,
    ) -> list[EvidenceEventRow]:
        statement = select(EvidenceEventRow).where(EvidenceEventRow.tenant_id == tenant_id)
        if project_id is not None:
            statement = statement.where(EvidenceEventRow.project_id == project_id)
        if kinds:
            statement = statement.where(EvidenceEventRow.kind.in_(kinds))
        if before is not None:
            statement = statement.where(
                tuple_(EvidenceEventRow.created_at, EvidenceEventRow.id) < tuple_(*before)
            )
        statement = statement.order_by(
            EvidenceEventRow.created_at.desc(), EvidenceEventRow.id.desc()
        ).limit(limit)
        return list((await self._session.execute(statement)).scalars())
