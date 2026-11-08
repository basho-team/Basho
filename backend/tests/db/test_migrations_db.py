"""Migração 0001: upgrade -> downgrade -> upgrade em banco exclusivo."""

import psycopg
import pytest
from sqlalchemy.engine import URL

from db_support import run_alembic

pytestmark = pytest.mark.db

TABLE_EXISTS_SQL = "SELECT to_regclass('public.evidence_events') IS NOT NULL"
FUNCTION_EXISTS_SQL = (
    "SELECT EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'evidence_events_reject_mutation')"
)


def _scalar(url: URL, sql: str) -> object:
    dsn = url.set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(dsn) as connection:
        row = connection.execute(sql).fetchone()
    assert row is not None
    return row[0]


def test_migration_is_reversible(migration_db_url: URL) -> None:
    # Arrange / Act / Assert por etapa
    run_alembic(migration_db_url, "upgrade", "head")
    assert _scalar(migration_db_url, TABLE_EXISTS_SQL) is True
    assert _scalar(migration_db_url, FUNCTION_EXISTS_SQL) is True

    run_alembic(migration_db_url, "downgrade", "base")
    assert _scalar(migration_db_url, TABLE_EXISTS_SQL) is False
    assert _scalar(migration_db_url, FUNCTION_EXISTS_SQL) is False

    run_alembic(migration_db_url, "upgrade", "head")
    assert _scalar(migration_db_url, TABLE_EXISTS_SQL) is True
