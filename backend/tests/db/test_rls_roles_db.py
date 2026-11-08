"""RLS por tenant e roles de menor privilégio (issue #21, ADR-0003, ADR-0006).

Tudo aqui roda como os roles da aplicação (logins membros de ``basho_api`` e
``basho_worker``), com SQL cru — sem o ``EvidenceService`` —, para provar que o
isolamento e a imutabilidade valem no banco, não só na camada de serviço. As guardas de
catálogo leem como dono e falham se uma tabela nova entrar sem RLS ou com grant indevido.
"""

from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from basho.db import UnsafeDatabaseRoleError, assert_least_privilege, tenant_session
from basho.evidence import EvidenceService
from evidence_factories import fresh_ids, make_event

pytestmark = pytest.mark.db

Factory = async_sessionmaker[AsyncSession]
APP_ROLES = ["basho_api", "basho_worker"]
APPEND_ONLY_TABLES = [
    "evidence_events",
    "reporting_periods",
    "report_versions",
    "report_reviews",
    "audit_log",
    "tool_approval_requests",
    "tool_approval_decisions",
    "projects",
    "activities",
    "pending_items",
    "pending_answers",
    "artifact_approvals",
]
# Tabelas de infraestrutura sem dado de tenant: sem RLS e sem privilégio para a app.
INFRA_TABLES = ["alembic_version"]
PERMISSION_DENIED = "permission denied"
RLS_VIOLATION = "row-level security"
COUNT_ALL = "SELECT count(*) FROM evidence_events"
RAW_INSERT = (
    "INSERT INTO evidence_events (id, tenant_id, project_id, kind, source, actor, payload, "
    "content_hash, hash_version) VALUES (gen_random_uuid(), :tenant, gen_random_uuid(), "
    "'commit_observed', 'github', '{}'::jsonb, '{}'::jsonb, repeat('0', 64), 1)"
)


@pytest.fixture(params=["api", "worker"])
def app_factory(
    request: pytest.FixtureRequest,
    session_factory: Factory,
    worker_session_factory: Factory,
) -> Factory:
    """Parametriza os testes pelos dois roles da aplicação."""
    return session_factory if request.param == "api" else worker_session_factory


async def _append(factory: Factory, tenant_id: UUID, project_id: UUID) -> UUID:
    async with tenant_session(factory, tenant_id) as session:
        saved = await EvidenceService(session).append(
            make_event(tenant_id=tenant_id, project_id=project_id)
        )
    return saved.id


async def _scalar(session: AsyncSession, sql: str, **params: object) -> object:
    return (await session.execute(text(sql), params)).scalar_one()


async def _column(session: AsyncSession, sql: str, **params: object) -> list[object]:
    return list((await session.execute(text(sql), params)).scalars().all())


# --- imutabilidade pelo role da app -------------------------------------------------


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE evidence_events SET source_ref = 'x' WHERE id = :id",
        "DELETE FROM evidence_events WHERE id = :id",
        "TRUNCATE evidence_events",
    ],
)
async def test_app_role_cannot_update_delete_or_truncate_ledger(
    app_factory: Factory, statement: str
) -> None:
    # Arrange
    tenant_id, project_id = fresh_ids()
    event_id = await _append(app_factory, tenant_id, project_id)

    # Act / Assert
    with pytest.raises(ProgrammingError, match=PERMISSION_DENIED):
        async with tenant_session(app_factory, tenant_id) as session:
            await session.execute(text(statement), {"id": event_id})


@pytest.mark.parametrize(
    "statement",
    [
        "ALTER TABLE evidence_events DISABLE TRIGGER trg_evidence_events_append_only",
        "ALTER TABLE evidence_events NO FORCE ROW LEVEL SECURITY",
        "DROP POLICY evidence_events_tenant_isolation ON evidence_events",
        "DROP TABLE evidence_events",
    ],
)
async def test_app_role_cannot_weaken_ledger_defenses(app_factory: Factory, statement: str) -> None:
    # Act / Assert: só o dono altera trigger, RLS, policy ou a tabela
    with pytest.raises(ProgrammingError, match="must be owner"):
        async with app_factory() as session, session.begin():
            await session.execute(text(statement))


# --- isolamento de tenant -----------------------------------------------------------


async def test_tenant_a_does_not_read_rows_of_tenant_b_even_without_where(
    app_factory: Factory,
) -> None:
    # Arrange
    tenant_a, project_a = fresh_ids()
    tenant_b, project_b = fresh_ids()
    own_id = await _append(app_factory, tenant_a, project_a)
    foreign_id = await _append(app_factory, tenant_b, project_b)
    by_id = "SELECT count(*) FROM evidence_events WHERE id = :id"

    # Act
    async with tenant_session(app_factory, tenant_a) as session:
        visible_tenants = await _column(session, "SELECT DISTINCT tenant_id FROM evidence_events")
        foreign_hits = await _scalar(session, by_id, id=foreign_id)
        own_hits = await _scalar(session, by_id, id=own_id)

    # Assert
    assert visible_tenants == [tenant_a]
    assert foreign_hits == 0
    assert own_hits == 1


async def test_tenant_a_cannot_insert_row_for_tenant_b(app_factory: Factory) -> None:
    # Arrange
    tenant_a, _ = fresh_ids()
    tenant_b, _ = fresh_ids()

    # Act / Assert
    with pytest.raises(ProgrammingError, match=RLS_VIOLATION):
        async with tenant_session(app_factory, tenant_a) as session:
            await session.execute(text(RAW_INSERT), {"tenant": tenant_b})


async def test_session_without_tenant_sees_nothing(app_factory: Factory) -> None:
    # Arrange
    tenant_id, project_id = fresh_ids()
    await _append(app_factory, tenant_id, project_id)

    # Act
    async with app_factory() as session, session.begin():
        unset_count = await _scalar(session, COUNT_ALL)

    # Assert
    assert unset_count == 0


async def test_session_without_tenant_cannot_insert(app_factory: Factory) -> None:
    # Arrange
    tenant_id, _ = fresh_ids()

    # Act / Assert
    with pytest.raises(ProgrammingError, match=RLS_VIOLATION):
        async with app_factory() as session, session.begin():
            await session.execute(text(RAW_INSERT), {"tenant": tenant_id})


async def test_tenant_does_not_leak_to_next_transaction_on_same_connection(
    app_factory: Factory,
) -> None:
    # Arrange: uma única conexão física (como uma conexão reaproveitada do pool)
    tenant_id, project_id = fresh_ids()
    engine = app_factory.kw["bind"]
    async with engine.connect() as connection:
        async with AsyncSession(bind=connection) as session, session.begin():
            await session.execute(
                text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)}
            )
            await EvidenceService(session).append(
                make_event(tenant_id=tenant_id, project_id=project_id)
            )
        pid_first = (await connection.execute(text("SELECT pg_backend_pid()"))).scalar_one()

        # Act: próxima transação na MESMA conexão, sem tenant_session
        leftover = (
            await connection.execute(text("SELECT current_setting('app.tenant_id', true)"))
        ).scalar_one()
        count_after = (await connection.execute(text(COUNT_ALL))).scalar_one()
        pid_second = (await connection.execute(text("SELECT pg_backend_pid()"))).scalar_one()
        await connection.rollback()

    # Assert
    assert pid_first == pid_second
    assert leftover in ("", None)
    assert count_after == 0


async def test_invalid_tenant_setting_fails_closed(app_factory: Factory) -> None:
    # Act / Assert: valor inválido gera erro no cast, nunca amplia a visibilidade
    with pytest.raises(DBAPIError, match="uuid"):
        async with app_factory() as session, session.begin():
            await session.execute(text("SELECT set_config('app.tenant_id', 'nope', true)"))
            await session.execute(text(COUNT_ALL))


# --- guardas de catálogo ------------------------------------------------------------

UNPROTECTED_TABLES_SQL = """
    SELECT c.relname
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
      AND c.relname <> ALL(CAST(:infra AS text[]))
      AND NOT (c.relrowsecurity AND c.relforcerowsecurity
               AND EXISTS (SELECT 1 FROM pg_policy p WHERE p.polrelid = c.oid))
"""

FORBIDDEN_PRIVILEGES_SQL = """
    SELECT r.role || ' ' || c.relname || ' ' || p.priv
    FROM unnest(CAST(:roles AS text[])) AS r(role)
    CROSS JOIN pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    CROSS JOIN unnest(ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE',
                            'REFERENCES', 'TRIGGER']) AS p(priv)
    WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
      AND has_table_privilege(r.role, c.oid, p.priv)
      AND (p.priv IN ('DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER')
           OR (p.priv = 'UPDATE' AND c.relname = ANY(CAST(:append_only AS text[])))
           OR c.relname = ANY(CAST(:infra AS text[])))
"""

RISKY_ROLES_SQL = """
    SELECT rolname FROM pg_roles
    WHERE rolname = ANY(CAST(:roles AS text[]))
      AND (rolsuper OR rolbypassrls OR rolcreaterole OR rolcreatedb OR rolcanlogin
           OR has_schema_privilege(oid, 'public', 'CREATE'))
"""


async def test_every_business_table_has_forced_rls_and_a_policy(
    owner_session_factory: Factory,
) -> None:
    # Act
    async with owner_session_factory() as session:
        unprotected = await _column(session, UNPROTECTED_TABLES_SQL, infra=INFRA_TABLES)

    # Assert
    assert unprotected == []


async def test_app_roles_have_no_destructive_privileges(owner_session_factory: Factory) -> None:
    # Act: DELETE/TRUNCATE em nada; UPDATE em nada append-only; nada em infraestrutura
    async with owner_session_factory() as session:
        violations = await _column(
            session,
            FORBIDDEN_PRIVILEGES_SQL,
            roles=APP_ROLES,
            append_only=APPEND_ONLY_TABLES,
            infra=INFRA_TABLES,
        )

    # Assert
    assert violations == []


async def test_app_roles_exist_and_are_unprivileged(owner_session_factory: Factory) -> None:
    # Act
    async with owner_session_factory() as session:
        risky = await _column(session, RISKY_ROLES_SQL, roles=APP_ROLES)
        existing = await _scalar(
            session,
            "SELECT count(*) FROM pg_roles WHERE rolname = ANY(CAST(:roles AS text[]))",
            roles=APP_ROLES,
        )

    # Assert
    assert existing == len(APP_ROLES)
    assert risky == []


async def test_app_login_is_not_superuser_nor_member_of_table_owner(
    app_factory: Factory,
) -> None:
    # Arrange
    sql = """
        SELECT r.rolsuper OR r.rolbypassrls OR pg_has_role(current_user, c.relowner, 'MEMBER')
        FROM pg_class c, pg_roles r
        WHERE c.relname = 'evidence_events' AND r.rolname = current_user
    """

    # Act
    async with app_factory() as session:
        privileged = await _scalar(session, sql)

    # Assert
    assert privileged is False


async def test_least_privilege_check_accepts_app_login(app_factory: Factory) -> None:
    # Act / Assert: não levanta
    await assert_least_privilege(app_factory.kw["bind"])


async def test_least_privilege_check_rejects_owner_connection(owner_engine: AsyncEngine) -> None:
    # Act / Assert
    with pytest.raises(UnsafeDatabaseRoleError):
        await assert_least_privilege(owner_engine)
