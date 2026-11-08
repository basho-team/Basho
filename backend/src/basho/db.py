"""Infraestrutura de banco: engine, sessões e contexto de tenant (ADR-0006)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

TENANT_SETTING = "app.tenant_id"


def create_engine(database_url: str) -> AsyncEngine:
    """Cria o engine assíncrono. A URL usa o driver ``postgresql+psycopg://``."""
    return create_async_engine(database_url, pool_pre_ping=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def tenant_session(
    factory: async_sessionmaker[AsyncSession], tenant_id: UUID
) -> AsyncIterator[AsyncSession]:
    """Sessão transacional com ``app.tenant_id`` definido (base para a RLS da #21).

    Faz commit ao sair sem erro e rollback em exceção. O ``set_config`` com
    ``is_local=true`` vale só para esta transação.
    """
    async with factory() as session, session.begin():
        await session.execute(
            text("SELECT set_config(:name, :tenant, true)"),
            {"name": TENANT_SETTING, "tenant": str(tenant_id)},
        )
        yield session
