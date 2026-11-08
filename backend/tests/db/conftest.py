"""Fixtures de integração com Postgres.

Usa ``TEST_DATABASE_URL`` (fallback ``DATABASE_URL``) só para descobrir servidor e
credenciais; os testes rodam em bancos dedicados (``basho_test*``) recriados a cada
sessão, sem tocar no banco de dev. Sem banco acessível, os testes são pulados.
"""

from collections.abc import AsyncIterator, Iterator

import pytest
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from basho.db import create_engine, create_session_factory
from db_support import base_url, recreate_database, run_alembic

LEDGER_DB_NAME = "basho_test"
MIGRATION_DB_NAME = "basho_test_migrations"


@pytest.fixture(scope="session")
def migrated_ledger_url() -> URL:
    """Banco ``basho_test`` com as migrações aplicadas (head)."""
    url = recreate_database(base_url(), LEDGER_DB_NAME)
    run_alembic(url, "upgrade", "head")
    return url


@pytest.fixture
def migration_db_url() -> Iterator[URL]:
    """Banco vazio e exclusivo para o teste de migração reversível."""
    yield recreate_database(base_url(), MIGRATION_DB_NAME)


@pytest.fixture
async def engine(migrated_ledger_url: URL) -> AsyncIterator[AsyncEngine]:
    created = create_engine(migrated_ledger_url.render_as_string(hide_password=False))
    yield created
    await created.dispose()


@pytest.fixture
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return create_session_factory(engine)
