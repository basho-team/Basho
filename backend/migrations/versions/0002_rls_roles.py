"""Roles de menor privilégio e RLS por tenant em evidence_events (ADR-0003, ADR-0006).

Cria os roles ``basho_api`` e ``basho_worker`` como **grupos NOLOGIN** (detentores de
privilégio, sem senha). Os usuários de login de cada ambiente são criados fora das
migrações (ver ``backend/README.md``) e recebem ``GRANT basho_api TO <login>``. Nenhum
segredo passa por aqui.

``evidence_events`` passa a ter RLS habilitada e **forçada** (vale também para o dono),
com política por ``app.tenant_id`` definido por transação (``basho.db.tenant_session``).
Os roles da aplicação só têm ``SELECT``/``INSERT`` — nunca ``UPDATE``/``DELETE``/``TRUNCATE``.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-07
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLES = ("basho_api", "basho_worker")
TENANT_PREDICATE = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"
"""``NULLIF``: após o fim da transação o setting volta como ``''``; sem tenant ⇒ NULL ⇒
nenhuma linha visível e nenhum INSERT aceito (fail closed)."""


def _create_role_if_missing(role: str) -> None:
    # Roles são objetos do cluster: podem já existir (outro banco do mesmo servidor).
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                CREATE ROLE {role} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
                    NOREPLICATION NOBYPASSRLS;
            END IF;
        END
        $$
        """
    )


def _drop_role_if_unused(role: str) -> None:
    # Só remove se não restar privilégio/objeto em nenhum banco nem membro de login.
    op.execute(
        f"""
        DO $$
        DECLARE
            role_oid oid := (SELECT oid FROM pg_roles WHERE rolname = '{role}');
        BEGIN
            IF role_oid IS NOT NULL
               AND NOT EXISTS (SELECT 1 FROM pg_shdepend WHERE refobjid = role_oid)
               AND NOT EXISTS (SELECT 1 FROM pg_auth_members WHERE roleid = role_oid)
            THEN
                EXECUTE format('DROP ROLE %I', '{role}');
            END IF;
        END
        $$
        """
    )


def upgrade() -> None:
    roles = ", ".join(APP_ROLES)
    for role in APP_ROLES:
        _create_role_if_missing(role)

    op.execute(f"GRANT USAGE ON SCHEMA public TO {roles}")
    op.execute("REVOKE ALL ON evidence_events FROM PUBLIC")
    op.execute(f"REVOKE ALL ON evidence_events FROM {roles}")
    op.execute(f"GRANT SELECT, INSERT ON evidence_events TO {roles}")

    op.execute("ALTER TABLE evidence_events ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE evidence_events FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY evidence_events_tenant_isolation ON evidence_events "
        f"USING ({TENANT_PREDICATE}) WITH CHECK ({TENANT_PREDICATE})"
    )


def downgrade() -> None:
    roles = ", ".join(APP_ROLES)
    op.execute("DROP POLICY evidence_events_tenant_isolation ON evidence_events")
    op.execute("ALTER TABLE evidence_events NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE evidence_events DISABLE ROW LEVEL SECURITY")
    op.execute(f"REVOKE ALL ON evidence_events FROM {roles}")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {roles}")
    for role in APP_ROLES:
        _drop_role_if_unused(role)
