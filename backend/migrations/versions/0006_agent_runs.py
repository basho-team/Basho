"""Cria agent_runs (estado + fila do agente) e agent_calls (custo/latência por chamada).

``agent_runs`` é a própria fila (architecture.md §8, sem Redis): o worker reserva com
``SELECT ... FOR UPDATE SKIP LOCKED`` os runs ``queued`` com ``run_after <= now()``. O estado é
mutável, mas só o ``basho_worker`` atualiza, e só as colunas de execução (GRANT por coluna); a API
(``basho_api``) só cria e lê. Transições válidas são decididas em código (``transition_run``).

``agent_calls`` é append-only: um ``CallRecord`` do Maker por chamada ao modelo (modelo, versão do
prompt, tokens, latência, custo estimado). Sem conteúdo de prompt nem resposta (ADR-0006).

Cadeia provisória: 0004 → 0006 (a 0005 é de projetos/pendências; o merge ajusta o
``down_revision`` para '0005'). Roles vêm da 0002; aqui só GRANT.

Revision ID: 0006
Revises: 0004
Create Date: 2026-11-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Valores congelados (espelham RunStatus/TaskKind/ArtifactStatus em 2026-11-08).
_RUN_STATUSES = ("queued", "running", "awaiting_input", "completed", "failed")
_TASK_KINDS = ("research_report", "coordination", "technical_fiscal", "investigation")
_ARTIFACT_STATUSES = ("draft", "verified", "needs_human")

_TABLES = ("agent_runs", "agent_calls")
_WORKER_UPDATABLE = (
    "status",
    "attempts",
    "error",
    "run_after",
    "updated_at",
    "artifact_event_id",
    "verification_event_id",
    "artifact_status",
)
_GRANTS: dict[str, dict[str, str]] = {
    "agent_runs": {
        "basho_api": "SELECT, INSERT",
        "basho_worker": f"SELECT, UPDATE ({', '.join(_WORKER_UPDATABLE)})",
    },
    "agent_calls": {"basho_api": "SELECT", "basho_worker": "SELECT, INSERT"},
}
_TENANT_EXPR = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def _in_list(values: Sequence[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _create_tables() -> None:
    op.execute(
        f"""
        CREATE TABLE agent_runs (
            id                     uuid        PRIMARY KEY,
            tenant_id              uuid        NOT NULL,
            project_id             uuid        NOT NULL,
            task_kind              text        NOT NULL,
            prompt_version         text        NOT NULL,
            status                 text        NOT NULL,
            correlation_id         uuid        NOT NULL,
            parent_run_id          uuid,
            idempotency_key        text        NOT NULL,
            dedupe_key             text        NOT NULL,
            attempts               integer     NOT NULL DEFAULT 0,
            max_attempts           integer     NOT NULL,
            error                  jsonb,
            task_input             jsonb       NOT NULL,
            requested_by           uuid,
            is_synthetic           boolean     NOT NULL DEFAULT false,
            run_after              timestamptz NOT NULL DEFAULT now(),
            artifact_event_id      uuid,
            verification_event_id  uuid,
            artifact_status        text,
            created_at             timestamptz NOT NULL DEFAULT now(),
            updated_at             timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_agent_runs_status CHECK (status IN ({_in_list(_RUN_STATUSES)})),
            CONSTRAINT ck_agent_runs_task_kind CHECK (task_kind IN ({_in_list(_TASK_KINDS)})),
            CONSTRAINT ck_agent_runs_artifact_status CHECK (
                artifact_status IS NULL OR artifact_status IN ({_in_list(_ARTIFACT_STATUSES)})
            ),
            CONSTRAINT ck_agent_runs_prompt_version CHECK (prompt_version ~ '^v[0-9]+$'),
            CONSTRAINT ck_agent_runs_attempts
                CHECK (attempts >= 0 AND max_attempts >= 1 AND attempts <= max_attempts),
            CONSTRAINT ck_agent_runs_failed_has_error
                CHECK (status <> 'failed' OR error IS NOT NULL),
            CONSTRAINT ck_agent_runs_completed_no_error
                CHECK (status <> 'completed' OR error IS NULL),
            CONSTRAINT uq_agent_runs_tenant_id UNIQUE (tenant_id, id),
            CONSTRAINT uq_agent_runs_idempotency UNIQUE (tenant_id, idempotency_key)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_agent_runs_queue ON agent_runs (run_after, created_at) "
        "WHERE status = 'queued'"
    )
    op.execute("CREATE INDEX ix_agent_runs_tenant_project ON agent_runs (tenant_id, project_id)")
    # Limite de custo (ADR-0006 §6): no máximo um run ativo por tarefa (hash de tipo+entrada).
    op.execute(
        "CREATE UNIQUE INDEX uq_agent_runs_active_task ON agent_runs (tenant_id, dedupe_key) "
        "WHERE status IN ('queued', 'running')"
    )
    op.execute(
        "CREATE INDEX ix_agent_runs_active_requester ON agent_runs (tenant_id, requested_by) "
        "WHERE status IN ('queued', 'running')"
    )
    op.execute(
        """
        CREATE TABLE agent_calls (
            id                           uuid          PRIMARY KEY,
            tenant_id                    uuid          NOT NULL,
            run_id                       uuid          NOT NULL,
            attempt                      integer       NOT NULL,
            seq                          integer       NOT NULL,
            model                        text          NOT NULL,
            prompt_version               text          NOT NULL,
            stop_reason                  text,
            input_tokens                 integer       NOT NULL,
            output_tokens                integer       NOT NULL,
            cache_read_input_tokens      integer       NOT NULL,
            cache_creation_input_tokens  integer       NOT NULL,
            latency_ms                   integer       NOT NULL,
            request_id                   text,
            estimated_cost_usd           numeric(12,6),
            created_at                   timestamptz   NOT NULL DEFAULT now(),
            CONSTRAINT ck_agent_calls_non_negative CHECK (
                attempt >= 1 AND seq >= 0 AND input_tokens >= 0 AND output_tokens >= 0
                AND cache_read_input_tokens >= 0 AND cache_creation_input_tokens >= 0
                AND latency_ms >= 0 AND (estimated_cost_usd IS NULL OR estimated_cost_usd >= 0)
            ),
            CONSTRAINT uq_agent_calls_run_attempt_seq UNIQUE (run_id, attempt, seq),
            CONSTRAINT fk_agent_calls_run_same_tenant
                FOREIGN KEY (tenant_id, run_id) REFERENCES agent_runs (tenant_id, id)
        )
        """
    )
    op.execute("CREATE INDEX ix_agent_calls_tenant_run ON agent_calls (tenant_id, run_id)")


def _protect_tables() -> None:
    # agent_calls é append-only; basho_reject_mutation() vem da 0003.
    op.execute(
        "CREATE TRIGGER trg_agent_calls_append_only BEFORE UPDATE OR DELETE ON agent_calls "
        "FOR EACH ROW EXECUTE FUNCTION basho_reject_mutation()"
    )
    op.execute(
        "CREATE TRIGGER trg_agent_calls_no_truncate BEFORE TRUNCATE ON agent_calls "
        "FOR EACH STATEMENT EXECUTE FUNCTION basho_reject_mutation()"
    )
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant_isolation ON {table} "
            f"USING (tenant_id = {_TENANT_EXPR}) WITH CHECK (tenant_id = {_TENANT_EXPR})"
        )
        op.execute(f"REVOKE ALL ON {table} FROM PUBLIC")
        for role, privileges in _GRANTS[table].items():
            op.execute(f"GRANT {privileges} ON {table} TO {role}")


def upgrade() -> None:
    _create_tables()
    _protect_tables()


def downgrade() -> None:
    bind = op.get_bind()
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
    if bind.execute(sa.text("SELECT EXISTS (SELECT 1 FROM agent_calls)")).scalar_one():
        raise RuntimeError("downgrade recusado: agent_calls contém linhas e é append-only")
    # agent_runs é estado de execução (não evidência); recusa se houver run em andamento.
    running = sa.text("SELECT EXISTS (SELECT 1 FROM agent_runs WHERE status = 'running')")
    if bind.execute(running).scalar_one():
        raise RuntimeError("downgrade recusado: há runs em execução em agent_runs")
    op.execute("DROP TABLE agent_calls")
    op.execute("DROP TABLE agent_runs")
