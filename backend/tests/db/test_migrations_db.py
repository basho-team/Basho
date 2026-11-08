"""Migração 0001: upgrade -> downgrade -> upgrade em banco exclusivo."""

import psycopg
import pytest
from sqlalchemy.engine import URL

from db_support import run_alembic, run_alembic_raw

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


def test_downgrade_is_refused_when_ledger_has_rows(migration_db_url: URL) -> None:
    # Arrange
    run_alembic(migration_db_url, "upgrade", "head")
    dsn = migration_db_url.set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(dsn) as connection:
        connection.execute(
            "INSERT INTO evidence_events (id, tenant_id, project_id, kind, source, actor, "
            "payload, content_hash, hash_version) VALUES (gen_random_uuid(), gen_random_uuid(), "
            "gen_random_uuid(), 'commit_observed', 'github', '{}'::jsonb, '{}'::jsonb, "
            "repeat('0', 64), 1)"
        )

    # Act
    result = run_alembic_raw(migration_db_url, "downgrade", "base")

    # Assert
    assert result.returncode != 0
    assert "append-only" in result.stderr
    assert _scalar(migration_db_url, TABLE_EXISTS_SQL) is True
