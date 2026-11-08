"""Fixtures de integração com Postgres.

Usa ``TEST_DATABASE_URL`` (fallback ``DATABASE_URL``) só para descobrir servidor e
credenciais do role dono/migração; os testes rodam em bancos dedicados (``basho_test*``)
recriados a cada sessão, sem tocar no banco de dev. Sem banco acessível, os testes são
pulados.

``session_factory`` conecta como um login membro de ``basho_api`` (o role da aplicação,
sujeito a RLS e sem UPDATE/DELETE/TRUNCATE). ``owner_session_factory`` usa o role dono,
só para testar as defesas que valem mesmo para ele (trigger, FORCE RLS).
"""

from collections.abc import AsyncIterator, Iterator

import pytest
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from basho.db import create_engine, create_session_factory
from db_support import base_url, provision_login_role, recreate_database, run_alembic

LEDGER_DB_NAME = "basho_test"
MIGRATION_DB_NAME = "basho_test_migrations"
API_LOGIN = "basho_test_api_login"
WORKER_LOGIN = "basho_test_worker_login"


@pytest.fixture(scope="session")
def migrated_ledger_url() -> URL:
    """Banco ``basho_test`` com as migrações aplicadas (head), como role dono."""
    url = recreate_database(base_url(), LEDGER_DB_NAME)
    run_alembic(url, "upgrade", "head")
    return url


@pytest.fixture(scope="session")
def api_url(migrated_ledger_url: URL) -> URL:
    return provision_login_role(migrated_ledger_url, API_LOGIN, "basho_api")


@pytest.fixture(scope="session")
def worker_url(migrated_ledger_url: URL) -> URL:
    return provision_login_role(migrated_ledger_url, WORKER_LOGIN, "basho_worker")


@pytest.fixture
def migration_db_url() -> Iterator[URL]:
    """Banco vazio e exclusivo para o teste de migração reversível."""
    yield recreate_database(base_url(), MIGRATION_DB_NAME)


async def _engine(url: URL) -> AsyncIterator[AsyncEngine]:
    created = create_engine(url.render_as_string(hide_password=False))
    yield created
    await created.dispose()


@pytest.fixture
async def engine(api_url: URL) -> AsyncIterator[AsyncEngine]:
    async for created in _engine(api_url):
        yield created


@pytest.fixture
async def worker_engine(worker_url: URL) -> AsyncIterator[AsyncEngine]:
    async for created in _engine(worker_url):
        yield created


@pytest.fixture
async def owner_engine(migrated_ledger_url: URL) -> AsyncIterator[AsyncEngine]:
    async for created in _engine(migrated_ledger_url):
        yield created


@pytest.fixture
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Sessões como role da aplicação (``basho_api``)."""
    return create_session_factory(engine)


@pytest.fixture
def worker_session_factory(worker_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return create_session_factory(worker_engine)


@pytest.fixture
def owner_session_factory(owner_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Sessões como role dono/migração (só para testar defesas de última camada)."""
    return create_session_factory(owner_engine)
