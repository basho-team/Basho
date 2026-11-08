"""Cria audit_log e as tabelas de aprovação de tools external (ADR-0005, ADR-0006).

As três tabelas são append-only (trigger bloqueia UPDATE/DELETE/TRUNCATE), têm ``tenant_id``
com RLS forçada e os roles da aplicação só recebem SELECT e INSERT. A aprovação é derivada:
pedido sem linha em ``tool_approval_decisions`` está pendente.

Cadeia combinada: 0002_rls_roles (#21) → 0003_reports (#39) → 0004. Enquanto 0002/0003 não
estiverem na main, ``down_revision`` aponta para 0001; quem mergear depois ajusta para 0003.
Os roles são criados só se ainda não existirem (a 0002 é a dona deles).

Revision ID: 0004
Revises: 0001
Create Date: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Valores congelados nesta migração (espelham os enums de audit/agent em 2026-11-07).
_EVENT_TYPES = ("tool_call", "approval_decided")
_ACTOR_TYPES = ("agent", "user", "system")
_LEVELS = ("read", "write_internal", "external", "formal")
_DECISIONS = ("allowed", "denied", "pending_approval", "approved", "rejected")
_OUTCOMES = ("ok", "error", "not_executed")
_APPROVAL_DECISIONS = ("approved", "rejected")
_CODE = "^[a-z][a-z0-9_]{2,63}$"

_TABLES = ("audit_log", "tool_approval_requests", "tool_approval_decisions")
_APP_ROLES = ("basho_api", "basho_worker")
_TENANT_EXPR = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def _in_list(values: Sequence[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _create_tables() -> None:
    op.execute(
        f"""
        CREATE TABLE audit_log (
            id                uuid        PRIMARY KEY,
            tenant_id         uuid        NOT NULL,
            event_type        text        NOT NULL,
            actor_type        text        NOT NULL,
            actor_id          uuid,
            run_id            uuid,
            tool              text        NOT NULL,
            level             text,
            decision          text        NOT NULL,
            outcome           text        NOT NULL,
            reason_code       text,
            input_keys        text[]      NOT NULL DEFAULT '{{}}',
            input_size_bytes  integer     NOT NULL,
            approval_id       uuid,
            created_at        timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_audit_log_event_type CHECK (event_type IN ({_in_list(_EVENT_TYPES)})),
            CONSTRAINT ck_audit_log_actor_type CHECK (actor_type IN ({_in_list(_ACTOR_TYPES)})),
            CONSTRAINT ck_audit_log_level CHECK (level IS NULL OR level IN ({_in_list(_LEVELS)})),
            CONSTRAINT ck_audit_log_decision CHECK (decision IN ({_in_list(_DECISIONS)})),
            CONSTRAINT ck_audit_log_outcome CHECK (outcome IN ({_in_list(_OUTCOMES)})),
            CONSTRAINT ck_audit_log_tool CHECK (tool ~ '{_CODE}'),
            CONSTRAINT ck_audit_log_reason_code
                CHECK (reason_code IS NULL OR reason_code ~ '{_CODE}'),
            CONSTRAINT ck_audit_log_input_size CHECK (input_size_bytes >= 0)
        )
        """
    )
    op.execute("CREATE INDEX ix_audit_log_tenant_run ON audit_log (tenant_id, run_id, created_at)")
    op.execute("CREATE INDEX ix_audit_log_tenant_created ON audit_log (tenant_id, created_at)")
    op.execute(
        f"""
        CREATE TABLE tool_approval_requests (
            id          uuid        PRIMARY KEY,
            tenant_id   uuid        NOT NULL,
            run_id      uuid        NOT NULL,
            tool        text        NOT NULL,
            level       text        NOT NULL,
            arguments   jsonb       NOT NULL,
            created_at  timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_tool_approval_requests_level CHECK (level = 'external'),
            CONSTRAINT ck_tool_approval_requests_tool CHECK (tool ~ '{_CODE}'),
            CONSTRAINT uq_tool_approval_requests_tenant_id UNIQUE (tenant_id, id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_tool_approval_requests_tenant_run "
        "ON tool_approval_requests (tenant_id, run_id)"
    )
    op.execute(
        f"""
        CREATE TABLE tool_approval_decisions (
            id           uuid        PRIMARY KEY,
            tenant_id    uuid        NOT NULL,
            approval_id  uuid        NOT NULL,
            decision     text        NOT NULL,
            decided_by   uuid        NOT NULL,
            created_at   timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_tool_approval_decisions_decision
                CHECK (decision IN ({_in_list(_APPROVAL_DECISIONS)})),
            CONSTRAINT uq_tool_approval_decisions_approval_id UNIQUE (approval_id),
            CONSTRAINT fk_tool_approval_decisions_request_same_tenant
                FOREIGN KEY (tenant_id, approval_id)
                REFERENCES tool_approval_requests (tenant_id, id)
        )
        """
    )


def _protect_tables() -> None:
    op.execute(
        """
        CREATE FUNCTION tool_audit_reject_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION '% is append-only (% not allowed)', TG_TABLE_NAME, TG_OP
                USING ERRCODE = 'restrict_violation';
        END;
        $$
        """
    )
    for role in _APP_ROLES:
        create_if_missing = (
            f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') "  # noqa: S608
            f"THEN CREATE ROLE {role} NOLOGIN; END IF; END $$"
        )
        op.execute(create_if_missing)
    roles = ", ".join(_APP_ROLES)
    for table in _TABLES:
        op.execute(
            f"CREATE TRIGGER trg_{table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION tool_audit_reject_mutation()"
        )
        op.execute(
            f"CREATE TRIGGER trg_{table}_no_truncate BEFORE TRUNCATE ON {table} "
            "FOR EACH STATEMENT EXECUTE FUNCTION tool_audit_reject_mutation()"
        )
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant_isolation ON {table} "
            f"USING (tenant_id = {_TENANT_EXPR}) WITH CHECK (tenant_id = {_TENANT_EXPR})"
        )
        op.execute(f"REVOKE ALL ON {table} FROM PUBLIC")
        op.execute(f"GRANT SELECT, INSERT ON {table} TO {roles}")


def upgrade() -> None:
    _create_tables()
    _protect_tables()


def downgrade() -> None:
    bind = op.get_bind()
    for table in _TABLES:
        if bind.execute(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table})")).scalar_one():  # noqa: S608
            message = (
                f"downgrade recusado: {table} contém linhas e é append-only; "
                "o downgrade destruiria o histórico de auditoria."
            )
            raise RuntimeError(message)
    for table in reversed(_TABLES):
        op.execute(f"DROP TABLE {table}")
    op.execute("DROP FUNCTION tool_audit_reject_mutation()")
    # Os roles basho_api/basho_worker pertencem à 0002 (#21) e não são removidos aqui.
