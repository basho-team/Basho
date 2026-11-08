"""Migrações: upgrade -> downgrade -> upgrade em banco exclusivo (0001, 0002 e 0003)."""

import psycopg
import pytest
from sqlalchemy.engine import URL

from db_support import run_alembic, run_alembic_raw

pytestmark = pytest.mark.db

TABLE_EXISTS_SQL = "SELECT to_regclass('public.evidence_events') IS NOT NULL"
FUNCTION_EXISTS_SQL = (
    "SELECT EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'evidence_events_reject_mutation')"
)


REPORT_TABLES = ("reporting_periods", "report_versions", "report_reviews")
RLS_FORCED_SQL = (
    "SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE relname = 'evidence_events'"
)
POLICY_EXISTS_SQL = (
    "SELECT EXISTS (SELECT 1 FROM pg_policy WHERE polname = 'evidence_events_tenant_isolation')"
)
APP_CAN_SELECT_SQL = "SELECT has_table_privilege('basho_api', 'evidence_events', 'SELECT')"


def _report_tables_exist(url: URL) -> list[bool]:
    return [
        bool(_scalar(url, f"SELECT to_regclass('public.{table}') IS NOT NULL"))
        for table in REPORT_TABLES
    ]


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
    assert _report_tables_exist(migration_db_url) == [True, True, True]
    assert _scalar(migration_db_url, RLS_FORCED_SQL) is True
    assert _scalar(migration_db_url, POLICY_EXISTS_SQL) is True
    assert _scalar(migration_db_url, APP_CAN_SELECT_SQL) is True

    run_alembic(migration_db_url, "downgrade", "0001")
    assert _report_tables_exist(migration_db_url) == [False, False, False]
    assert _scalar(migration_db_url, RLS_FORCED_SQL) is False
    assert _scalar(migration_db_url, POLICY_EXISTS_SQL) is False
    assert _scalar(migration_db_url, APP_CAN_SELECT_SQL) is False

    run_alembic(migration_db_url, "upgrade", "head")
    assert _scalar(migration_db_url, RLS_FORCED_SQL) is True

    run_alembic(migration_db_url, "downgrade", "base")
    assert _scalar(migration_db_url, TABLE_EXISTS_SQL) is False
    assert _scalar(migration_db_url, FUNCTION_EXISTS_SQL) is False
    assert _report_tables_exist(migration_db_url) == [False, False, False]

    run_alembic(migration_db_url, "upgrade", "head")
    assert _scalar(migration_db_url, TABLE_EXISTS_SQL) is True
    assert _report_tables_exist(migration_db_url) == [True, True, True]
    assert _scalar(migration_db_url, POLICY_EXISTS_SQL) is True


def test_downgrade_is_refused_when_ledger_has_rows(migration_db_url: URL) -> None:
    # Arrange
    run_alembic(migration_db_url, "upgrade", "head")
    dsn = migration_db_url.set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(dsn) as connection:
        # FORCE RLS: o tenant precisa estar definido mesmo para o dono não-superuser.
        connection.execute("SELECT set_config('app.tenant_id', gen_random_uuid()::text, true)")
        connection.execute(
            "INSERT INTO evidence_events (id, tenant_id, project_id, kind, source, actor, "
            "payload, content_hash, hash_version) VALUES (gen_random_uuid(), "
            "current_setting('app.tenant_id')::uuid, "
            "gen_random_uuid(), 'commit_observed', 'github', '{}'::jsonb, '{}'::jsonb, "
            "repeat('0', 64), 1)"
        )

    # Act
    result = run_alembic_raw(migration_db_url, "downgrade", "base")

    # Assert
    assert result.returncode != 0
    assert "append-only" in result.stderr
    assert _scalar(migration_db_url, TABLE_EXISTS_SQL) is True


def test_downgrade_is_refused_when_report_versions_has_rows(migration_db_url: URL) -> None:
    # Arrange: FORCE RLS exige app.tenant_id na mesma transação do INSERT
    run_alembic(migration_db_url, "upgrade", "head")
    dsn = migration_db_url.set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(dsn) as connection:
        connection.execute(
            "SELECT set_config('app.tenant_id', '00000000-0000-0000-0000-0000000000a1', true)"
        )
        connection.execute(
            "INSERT INTO evidence_events (id, tenant_id, project_id, kind, source, actor, "
            "payload, content_hash, hash_version) VALUES "
            "('00000000-0000-0000-0000-0000000000e1', '00000000-0000-0000-0000-0000000000a1', "
            "'00000000-0000-0000-0000-0000000000b1', 'activity_record', 'system', '{}'::jsonb, "
            "'{}'::jsonb, repeat('0', 64), 1)"
        )
        connection.execute(
            "INSERT INTO reporting_periods (id, tenant_id, start_date, end_date, timezone, "
            "periodicity) VALUES ('00000000-0000-0000-0000-0000000000c1', "
            "'00000000-0000-0000-0000-0000000000a1', '2026-10-01', '2026-10-31', "
            "'America/Sao_Paulo', 'monthly')"
        )
        connection.execute(
            "INSERT INTO report_versions (id, tenant_id, project_id, researcher_id, "
            "reporting_period_id, number, draft, claim_ids, experiment_ids, missing_ids, "
            "content_hash, evidence_event_id, cited_evidence_ids, created_at) VALUES "
            "('00000000-0000-0000-0000-0000000000d1', '00000000-0000-0000-0000-0000000000a1', "
            "'00000000-0000-0000-0000-0000000000b1', '00000000-0000-0000-0000-0000000000f1', "
            "'00000000-0000-0000-0000-0000000000c1', 1, '{}'::jsonb, '{}', '{}', '{}', "
            "repeat('0', 64), '00000000-0000-0000-0000-0000000000e1', '{}', now())"
        )

    # Act
    result = run_alembic_raw(migration_db_url, "downgrade", "base")

    # Assert
    assert result.returncode != 0
    assert "append-only" in result.stderr
    assert _report_tables_exist(migration_db_url) == [True, True, True]


PROJECT_TABLES = (
    "projects",
    "activities",
    "pending_items",
    "pending_answers",
    "artifact_approvals",
)


def _project_tables_exist(url: URL) -> list[bool]:
    return [
        bool(_scalar(url, f"SELECT to_regclass('public.{table}') IS NOT NULL"))
        for table in PROJECT_TABLES
    ]


def test_projects_migration_is_reversible(migration_db_url: URL) -> None:
    run_alembic(migration_db_url, "upgrade", "head")
    assert _project_tables_exist(migration_db_url) == [True] * len(PROJECT_TABLES)

    run_alembic(migration_db_url, "downgrade", "0004")
    assert _project_tables_exist(migration_db_url) == [False] * len(PROJECT_TABLES)

    run_alembic(migration_db_url, "upgrade", "head")
    assert _project_tables_exist(migration_db_url) == [True] * len(PROJECT_TABLES)


def test_downgrade_is_refused_when_projects_has_rows(migration_db_url: URL) -> None:
    # Arrange
    run_alembic(migration_db_url, "upgrade", "head")
    dsn = migration_db_url.set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(dsn) as connection:
        connection.execute(
            "SELECT set_config('app.tenant_id', '00000000-0000-0000-0000-0000000000a1', true)"
        )
        connection.execute(
            "INSERT INTO projects (id, tenant_id, name) VALUES (gen_random_uuid(), "
            "'00000000-0000-0000-0000-0000000000a1', 'Projeto sintético')"
        )

    # Act
    result = run_alembic_raw(migration_db_url, "downgrade", "0004")

    # Assert
    assert result.returncode != 0
    assert "append-only" in result.stderr
    assert _project_tables_exist(migration_db_url) == [True] * len(PROJECT_TABLES)
