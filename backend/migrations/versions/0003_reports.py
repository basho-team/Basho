"""Cria reporting_periods, report_versions e report_reviews (#39).

Persistência dos tipos de domínio de `basho.reports` (PR #43): `ReportVersion` e `ReportReview`.
Tabelas append-only (trigger + REVOKE) com RLS por tenant (ADR-0003, ADR-0006).

Revision ID: 0003
Revises: 0001
Create Date: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
# TODO(#21): trocar para "0002" ao rebasear sobre 0002_rls_roles da Sentinela
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Valores congelados nesta migração (espelham Periodicity de #41 e ReviewerRole/ReviewDecision
# do domínio de reports, PR #43, em 2026-11-08).
_PERIODICITIES = ("weekly", "biweekly", "monthly", "custom")
_REVIEWER_ROLES = ("researcher", "manager")
_DECISIONS = ("text_approved", "changes_requested")

_TABLES = ("reporting_periods", "report_versions", "report_reviews")
_ROLES = ("basho_api", "basho_worker")  # criados pela 0002 (#21); podem não existir ainda
_TENANT_EXPR = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def _in_list(values: Sequence[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _create_tables() -> None:
    op.execute(
        f"""
        CREATE TABLE reporting_periods (
            id           uuid        PRIMARY KEY,
            tenant_id    uuid        NOT NULL,
            start_date   date        NOT NULL,
            end_date     date        NOT NULL,
            timezone     text        NOT NULL,
            periodicity  text        NOT NULL,
            created_at   timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_reporting_periods_periodicity
                CHECK (periodicity IN ({_in_list(_PERIODICITIES)})),
            CONSTRAINT ck_reporting_periods_dates CHECK (end_date >= start_date),
            CONSTRAINT uq_reporting_periods_natural
                UNIQUE (tenant_id, start_date, end_date, timezone, periodicity),
            CONSTRAINT uq_reporting_periods_tenant_id UNIQUE (tenant_id, id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE report_versions (
            id                   uuid        PRIMARY KEY,
            tenant_id            uuid        NOT NULL,
            project_id           uuid        NOT NULL,
            researcher_id        uuid        NOT NULL,
            reporting_period_id  uuid        NOT NULL,
            number               integer     NOT NULL,
            supersedes_id        uuid,
            draft                jsonb       NOT NULL,
            claim_ids            uuid[]      NOT NULL,
            experiment_ids       uuid[]      NOT NULL,
            missing_ids          uuid[]      NOT NULL,
            change               jsonb,
            content_hash         char(64)    NOT NULL,
            evidence_event_id    uuid        NOT NULL,
            cited_evidence_ids   uuid[]      NOT NULL,
            is_synthetic         boolean     NOT NULL DEFAULT false,
            created_at           timestamptz NOT NULL,
            CONSTRAINT ck_report_versions_number CHECK (number >= 1),
            CONSTRAINT ck_report_versions_content_hash CHECK (content_hash ~ '^[0-9a-f]{64}$'),
            -- v1 não substitui nada nem tem ChangeRecord; v>1 tem os dois (ReportVersion, #43)
            CONSTRAINT ck_report_versions_lineage CHECK (
                (number = 1) = (supersedes_id IS NULL)
                AND (supersedes_id IS NULL) = (change IS NULL)
            ),
            CONSTRAINT uq_report_versions_tenant_id UNIQUE (tenant_id, id),
            CONSTRAINT uq_report_versions_series_number
                UNIQUE (tenant_id, project_id, researcher_id, reporting_period_id, number),
            CONSTRAINT uq_report_versions_series_id
                UNIQUE (tenant_id, project_id, researcher_id, reporting_period_id, id),
            -- uma versão só é substituída por UMA outra: impede fork da série
            CONSTRAINT uq_report_versions_supersedes UNIQUE (supersedes_id),
            CONSTRAINT fk_report_versions_period FOREIGN KEY (tenant_id, reporting_period_id)
                REFERENCES reporting_periods (tenant_id, id),
            CONSTRAINT fk_report_versions_evidence_event
                FOREIGN KEY (tenant_id, project_id, evidence_event_id)
                REFERENCES evidence_events (tenant_id, project_id, id),
            -- supersedes_id só aponta para versão da mesma série
            CONSTRAINT fk_report_versions_supersedes_same_series
                FOREIGN KEY
                    (tenant_id, project_id, researcher_id, reporting_period_id, supersedes_id)
                REFERENCES report_versions
                    (tenant_id, project_id, researcher_id, reporting_period_id, id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_report_versions_tenant_project_created "
        "ON report_versions (tenant_id, project_id, created_at, id)"
    )
    op.execute(
        f"""
        CREATE TABLE report_reviews (
            id                  uuid        PRIMARY KEY,
            tenant_id           uuid        NOT NULL,
            report_version_id   uuid        NOT NULL,
            reviewer_id         uuid        NOT NULL,
            reviewer_role       text        NOT NULL,
            decision            text        NOT NULL,
            comment             text,
            new_version_id      uuid,
            evidence_event_id   uuid        NOT NULL,
            is_synthetic        boolean     NOT NULL DEFAULT false,
            reviewed_at         timestamptz NOT NULL,
            CONSTRAINT ck_report_reviews_role
                CHECK (reviewer_role IN ({_in_list(_REVIEWER_ROLES)})),
            CONSTRAINT ck_report_reviews_decision CHECK (decision IN ({_in_list(_DECISIONS)})),
            CONSTRAINT fk_report_reviews_version FOREIGN KEY (tenant_id, report_version_id)
                REFERENCES report_versions (tenant_id, id),
            CONSTRAINT fk_report_reviews_new_version FOREIGN KEY (tenant_id, new_version_id)
                REFERENCES report_versions (tenant_id, id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_report_reviews_tenant_version_reviewed "
        "ON report_reviews (tenant_id, report_version_id, reviewed_at, id)"
    )


def _grant_if_role_exists(statement: str) -> str:
    """Bloco DO que aplica `statement` (com {role}) só para roles já existentes."""
    blocks = "\n".join(
        f"IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN "  # noqa: S608
        f"EXECUTE {_quote(statement.format(role=role))}; END IF;"
        for role in _ROLES
    )
    return f"DO $do$ BEGIN\n{blocks}\nEND $do$"


def _quote(sql: str) -> str:
    return "'" + sql.replace("'", "''") + "'"


def _protect_tables() -> None:
    op.execute(
        """
        CREATE FUNCTION basho_reject_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION '% is append-only (% not allowed)', TG_TABLE_NAME, TG_OP
                USING ERRCODE = 'restrict_violation';
        END;
        $$
        """
    )
    table_list = ", ".join(_TABLES)
    for table in _TABLES:
        op.execute(
            f"CREATE TRIGGER trg_{table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION basho_reject_mutation()"
        )
        op.execute(
            f"CREATE TRIGGER trg_{table}_no_truncate BEFORE TRUNCATE ON {table} "
            "FOR EACH STATEMENT EXECUTE FUNCTION basho_reject_mutation()"
        )
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant_isolation ON {table} "
            f"USING ({_TENANT_EXPR}) WITH CHECK ({_TENANT_EXPR})"
        )
    op.execute(f"REVOKE UPDATE, DELETE, TRUNCATE ON {table_list} FROM PUBLIC")
    op.execute(_grant_if_role_exists(f"GRANT SELECT, INSERT ON {table_list} TO {{role}}"))


def upgrade() -> None:
    _create_tables()
    _protect_tables()


def downgrade() -> None:
    # FORCE RLS esconderia as linhas do dono sem app.tenant_id: desliga a RLS (o dono pode)
    # antes de checar. Se a checagem recusar, a transação do Alembic desfaz tudo.
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    for table in ("report_reviews", "report_versions"):
        query = f"SELECT EXISTS (SELECT 1 FROM {table})"  # noqa: S608 -- nome fixo de _TABLES
        has_rows = op.get_bind().execute(sa.text(query))
        if has_rows.scalar_one():
            message = (
                f"downgrade recusado: {table} contém linhas e é append-only; "
                "o downgrade destruiria registros de revisão."
            )
            raise RuntimeError(message)
    for table in reversed(_TABLES):
        op.execute(f"DROP POLICY {table}_tenant_isolation ON {table}")
        op.execute(f"DROP TRIGGER trg_{table}_no_truncate ON {table}")
        op.execute(f"DROP TRIGGER trg_{table}_append_only ON {table}")
        op.execute(f"DROP TABLE {table}")
    op.execute("DROP FUNCTION basho_reject_mutation()")
