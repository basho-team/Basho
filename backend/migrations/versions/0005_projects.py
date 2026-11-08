"""Cria projetos, atividades, pendências, respostas e aprovações de artefato (#5).

Todas as tabelas são append-only (trigger bloqueia UPDATE/DELETE/TRUNCATE), têm ``tenant_id``
com RLS forçada e os roles da aplicação só recebem SELECT e INSERT. Estado é derivado:
pendência sem linha em ``pending_answers`` está aberta; artefato sem linha em
``artifact_approvals`` não tem decisão formal. Resposta e aprovação são ações humanas: o
``basho_worker`` (processo do agente) só lê essas duas tabelas (ADR-0005).

Cadeia: 0002_rls_roles (#21) → 0003_reports → 0004_tool_audit → 0005. Os roles são da 0002;
aqui só recebem GRANT. A 0006 (agent_runs/fila) vem depois desta.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Valores congelados nesta migração (espelham compliance/api_contracts.py em 2026-11-08).
_PENDING_KINDS = (
    "missing_justification",
    "missing_activity_record",
    "checker_disagreement",
    "approval_required",
    "tool_failure",
    "needs_review",
)
_APPROVAL_DECISIONS = ("approve", "reject")
_ANSWER_ROLES = ("researcher", "manager")

_TABLES = ("projects", "activities", "pending_items", "pending_answers", "artifact_approvals")
_HUMAN_ONLY = ("pending_answers", "artifact_approvals")
_TENANT_EXPR = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def _grants(table: str) -> dict[str, str]:
    worker = "SELECT" if table in _HUMAN_ONLY else "SELECT, INSERT"
    return {"basho_api": "SELECT, INSERT", "basho_worker": worker}


def _in_list(values: Sequence[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _create_projects() -> None:
    op.execute(
        """
        CREATE TABLE projects (
            id            uuid        PRIMARY KEY,
            tenant_id     uuid        NOT NULL,
            name          text        NOT NULL,
            description   text,
            is_synthetic  boolean     NOT NULL DEFAULT false,
            created_at    timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_projects_name CHECK (length(btrim(name)) > 0),
            CONSTRAINT uq_projects_tenant_id UNIQUE (tenant_id, id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE activities (
            id            uuid        PRIMARY KEY,
            tenant_id     uuid        NOT NULL,
            project_id    uuid        NOT NULL,
            title         text        NOT NULL,
            description   text,
            is_synthetic  boolean     NOT NULL DEFAULT false,
            created_at    timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_activities_title CHECK (length(btrim(title)) > 0),
            CONSTRAINT fk_activities_project_same_tenant
                FOREIGN KEY (tenant_id, project_id) REFERENCES projects (tenant_id, id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_activities_tenant_project_created "
        "ON activities (tenant_id, project_id, created_at)"
    )


def _create_pending() -> None:
    op.execute(
        f"""
        CREATE TABLE pending_items (
            id                     uuid        PRIMARY KEY,
            tenant_id              uuid        NOT NULL,
            project_id             uuid        NOT NULL,
            activity_id            uuid,
            kind                   text        NOT NULL,
            source_key             text        NOT NULL,
            title                  text        NOT NULL,
            question               text        NOT NULL,
            assignee_role          text        NOT NULL,
            artifact_event_id      uuid        NOT NULL,
            verification_event_id  uuid        NOT NULL,
            is_synthetic           boolean     NOT NULL DEFAULT false,
            created_at             timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_pending_items_kind CHECK (kind IN ({_in_list(_PENDING_KINDS)})),
            CONSTRAINT uq_pending_items_tenant_id UNIQUE (tenant_id, id),
            -- projeção idempotente: uma pendência por (veredito, item)
            CONSTRAINT uq_pending_items_source
                UNIQUE (tenant_id, verification_event_id, source_key),
            CONSTRAINT fk_pending_items_project_same_tenant
                FOREIGN KEY (tenant_id, project_id) REFERENCES projects (tenant_id, id),
            CONSTRAINT fk_pending_items_artifact_same_project
                FOREIGN KEY (tenant_id, project_id, artifact_event_id)
                REFERENCES evidence_events (tenant_id, project_id, id),
            CONSTRAINT fk_pending_items_verification_same_project
                FOREIGN KEY (tenant_id, project_id, verification_event_id)
                REFERENCES evidence_events (tenant_id, project_id, id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_pending_items_tenant_project_created "
        "ON pending_items (tenant_id, project_id, created_at)"
    )
    op.execute(
        "CREATE INDEX ix_pending_items_tenant_artifact "
        "ON pending_items (tenant_id, artifact_event_id)"
    )
    op.execute(
        f"""
        CREATE TABLE pending_answers (
            id                   uuid        PRIMARY KEY,
            tenant_id            uuid        NOT NULL,
            pending_item_id      uuid        NOT NULL,
            answer               text        NOT NULL,
            corrected_payload    jsonb,
            answered_by          uuid        NOT NULL,
            answered_role        text        NOT NULL,
            correction_event_id  uuid        NOT NULL,
            created_at           timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_pending_answers_role CHECK (answered_role IN ({_in_list(_ANSWER_ROLES)})),
            CONSTRAINT ck_pending_answers_answer CHECK (length(btrim(answer)) > 0),
            CONSTRAINT uq_pending_answers_item UNIQUE (pending_item_id),
            CONSTRAINT fk_pending_answers_item_same_tenant
                FOREIGN KEY (tenant_id, pending_item_id) REFERENCES pending_items (tenant_id, id)
        )
        """
    )


def _create_approvals() -> None:
    op.execute(
        f"""
        CREATE TABLE artifact_approvals (
            id                 uuid        PRIMARY KEY,
            tenant_id          uuid        NOT NULL,
            project_id         uuid        NOT NULL,
            artifact_event_id  uuid        NOT NULL,
            decision           text        NOT NULL,
            comment            text,
            approver_id        uuid        NOT NULL,
            evidence_event_id  uuid        NOT NULL,
            created_at         timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_artifact_approvals_decision
                CHECK (decision IN ({_in_list(_APPROVAL_DECISIONS)})),
            -- uma decisão formal por artefato
            CONSTRAINT uq_artifact_approvals_artifact UNIQUE (tenant_id, artifact_event_id),
            CONSTRAINT fk_artifact_approvals_artifact_same_project
                FOREIGN KEY (tenant_id, project_id, artifact_event_id)
                REFERENCES evidence_events (tenant_id, project_id, id),
            CONSTRAINT fk_artifact_approvals_event_same_project
                FOREIGN KEY (tenant_id, project_id, evidence_event_id)
                REFERENCES evidence_events (tenant_id, project_id, id)
        )
        """
    )


def _protect_tables() -> None:
    op.execute(
        """
        CREATE FUNCTION projects_reject_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION '% is append-only (% not allowed)', TG_TABLE_NAME, TG_OP
                USING ERRCODE = 'restrict_violation';
        END;
        $$
        """
    )
    for table in _TABLES:
        op.execute(
            f"CREATE TRIGGER trg_{table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION projects_reject_mutation()"
        )
        op.execute(
            f"CREATE TRIGGER trg_{table}_no_truncate BEFORE TRUNCATE ON {table} "
            "FOR EACH STATEMENT EXECUTE FUNCTION projects_reject_mutation()"
        )
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant_isolation ON {table} "
            f"USING (tenant_id = {_TENANT_EXPR}) WITH CHECK (tenant_id = {_TENANT_EXPR})"
        )
        op.execute(f"REVOKE ALL ON {table} FROM PUBLIC")
        for role, privileges in _grants(table).items():
            op.execute(f"GRANT {privileges} ON {table} TO {role}")


def upgrade() -> None:
    _create_projects()
    _create_pending()
    _create_approvals()
    _protect_tables()


def downgrade() -> None:
    bind = op.get_bind()
    for table in _TABLES:
        # Sem FORCE o dono enxerga todas as linhas; com FORCE e sem tenant veria 0 e apagaria.
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        if bind.execute(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table})")).scalar_one():  # noqa: S608
            message = (
                f"downgrade recusado: {table} contém linhas e é append-only; "
                "o downgrade destruiria o histórico."
            )
            raise RuntimeError(message)
    for table in reversed(_TABLES):
        op.execute(f"DROP TABLE {table}")
    op.execute("DROP FUNCTION projects_reject_mutation()")
    # Os roles basho_api/basho_worker pertencem à 0002 (#21) e não são removidos aqui.
