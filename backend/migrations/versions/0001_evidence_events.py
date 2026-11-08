"""Cria evidence_events, o ledger append-only (ADR-0003).

Revision ID: 0001
Revises:
Create Date: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Valores congelados nesta migração (espelham EventKind/EventSource em 2026-11-07).
_KINDS = (
    "commit_observed",
    "pull_request_observed",
    "issue_observed",
    "technical_justification",
    "activity_record",
    "formal_hours_declared",
    "expense_declared",
    "user_confirmation",
    "user_correction",
    "verification_result",
    "status_changed",
)
_SOURCES = ("github", "user", "formal_system", "agent", "system")


def _in_list(values: Sequence[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE evidence_events (
            id            uuid        PRIMARY KEY,
            tenant_id     uuid        NOT NULL,
            project_id    uuid        NOT NULL,
            kind          text        NOT NULL,
            source        text        NOT NULL,
            source_ref    text,
            actor         jsonb       NOT NULL,
            payload       jsonb       NOT NULL,
            content_hash  char(64)    NOT NULL,
            hash_version  smallint    NOT NULL,
            supersedes    uuid,
            is_synthetic  boolean     NOT NULL DEFAULT false,
            created_at    timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_evidence_events_kind CHECK (kind IN ({_in_list(_KINDS)})),
            CONSTRAINT ck_evidence_events_source CHECK (source IN ({_in_list(_SOURCES)})),
            CONSTRAINT ck_evidence_events_content_hash CHECK (content_hash ~ '^[0-9a-f]{{64}}$'),
            CONSTRAINT uq_evidence_events_tenant_project_id UNIQUE (tenant_id, project_id, id),
            -- supersedes só aponta para evento do mesmo tenant E do mesmo projeto
            CONSTRAINT fk_evidence_events_supersedes_same_project
                FOREIGN KEY (tenant_id, project_id, supersedes)
                REFERENCES evidence_events (tenant_id, project_id, id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_evidence_events_tenant_project_created "
        "ON evidence_events (tenant_id, project_id, created_at, id)"
    )
    op.execute(
        "CREATE INDEX ix_evidence_events_tenant_supersedes "
        "ON evidence_events (tenant_id, supersedes)"
    )
    op.execute(
        """
        CREATE FUNCTION evidence_events_reject_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'evidence_events is append-only (% not allowed)', TG_OP
                USING ERRCODE = 'restrict_violation';
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER trg_evidence_events_append_only "
        "BEFORE UPDATE OR DELETE ON evidence_events "
        "FOR EACH ROW EXECUTE FUNCTION evidence_events_reject_mutation()"
    )
    op.execute(
        "CREATE TRIGGER trg_evidence_events_no_truncate "
        "BEFORE TRUNCATE ON evidence_events "
        "FOR EACH STATEMENT EXECUTE FUNCTION evidence_events_reject_mutation()"
    )
    # Roles específicos (API/worker sem UPDATE/DELETE, RLS) ficam para a issue #21.
    op.execute("REVOKE UPDATE, DELETE, TRUNCATE ON evidence_events FROM PUBLIC")


def downgrade() -> None:
    has_rows = op.get_bind().execute(sa.text("SELECT EXISTS (SELECT 1 FROM evidence_events)"))
    if has_rows.scalar_one():
        message = (
            "downgrade recusado: evidence_events contém linhas e o ledger é append-only; "
            "o downgrade destruiria evidências."
        )
        raise RuntimeError(message)
    op.execute("DROP TRIGGER trg_evidence_events_no_truncate ON evidence_events")
    op.execute("DROP TRIGGER trg_evidence_events_append_only ON evidence_events")
    op.execute("DROP FUNCTION evidence_events_reject_mutation()")
    op.execute("DROP INDEX ix_evidence_events_tenant_supersedes")
    op.execute("DROP INDEX ix_evidence_events_tenant_project_created")
    op.execute("DROP TABLE evidence_events")
