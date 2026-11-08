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

# Verdadeiro se o role conectado anula a RLS: superuser, BYPASSRLS ou membro do dono de
# alguma tabela de ``public`` (o dono pode desligar trigger/RLS).
_UNSAFE_ROLE_SQL = text(
    """
    SELECT r.rolsuper OR r.rolbypassrls OR EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
          AND pg_has_role(current_user, c.relowner, 'MEMBER')
    )
    FROM pg_roles r WHERE r.rolname = current_user
    """
)


class UnsafeDatabaseRoleError(RuntimeError):
    """A aplicação está conectada com um role que ignora a RLS (ADR-0006)."""


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


async def assert_least_privilege(engine: AsyncEngine) -> None:
    """Falha rápido se ``DATABASE_URL`` usar superuser, BYPASSRLS ou o dono do schema.

    Para chamar no startup da API e do worker. A mensagem não inclui o nome do role nem a URL.
    """
    async with engine.connect() as connection:
        unsafe = (await connection.execute(_UNSAFE_ROLE_SQL)).scalar_one()
    if unsafe:
        message = (
            "DATABASE_URL usa um role que ignora a RLS (superuser, BYPASSRLS ou dono das "
            "tabelas); use o login da aplicação, membro de basho_api/basho_worker"
        )
        raise UnsafeDatabaseRoleError(message)


class DatabaseRoleSeparationError(RuntimeError):
    """O login não tem o role do processo ou tem também o do outro processo (ADR-0005/0006)."""


API_ROLE = "basho_api"
WORKER_ROLE = "basho_worker"

_MEMBERSHIP_SQL = text(
    "SELECT pg_has_role(current_user, :required, 'MEMBER'), "
    "pg_has_role(current_user, :forbidden, 'MEMBER')"
)


async def assert_process_role(engine: AsyncEngine, *, required: str, forbidden: str) -> None:
    """Falha rápido se o login não for membro de ``required`` ou for membro de ``forbidden``.

    Separa API e worker: um login nos dois grupos daria ao processo do agente as ações formais
    da API (ex.: ``report_reviews``, ``tool_approval_decisions``). A mensagem não cita o login.
    """
    async with engine.connect() as connection:
        member, overlaps = (
            await connection.execute(
                _MEMBERSHIP_SQL, {"required": required, "forbidden": forbidden}
            )
        ).one()
    if not member or overlaps:
        message = f"DATABASE_URL precisa ser um login membro de {required} e não de {forbidden}"
        raise DatabaseRoleSeparationError(message)
