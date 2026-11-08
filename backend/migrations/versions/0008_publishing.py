"""Cria project_links (links autorizados) e publications (fila de publicação) (ADR-0010).

``project_links``: fontes e destinos que um gerente autorizou colando um link (repositório do
GitHub, pasta do Drive, página do Notion). É a autorização do tenant exigida pela ADR-0005 para
ação externa rotineira: só se publica em link ativo cadastrado. Revogar muda ``status``; nada é
apagado. A API cria e atualiza só colunas de verificação/estado (GRANT por coluna).

``publications``: fila e estado de cada documento publicado (um por artefato por destino). O worker
(``basho_worker``) reserva com ``FOR UPDATE SKIP LOCKED`` e é o único que atualiza o resultado.
Unicidade (tenant, link, artefato, tipo) torna o enfileiramento idempotente.

Numeração: 0008 porque a 0007 está reservada à ponte agente→revisão (branch do núcleo); ao
mesclar, mantenha 0008 → 0007 só se aquela não existir.

Revision ID: 0008
Revises: 0006
Create Date: 2026-11-08
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Valores congelados (espelham LinkKind/LinkStatus/PublicationStatus em 2026-11-08).
_LINK_KINDS = ("github_repo", "drive_folder", "notion_page")
_LINK_STATUSES = ("active", "revoked")
_PUBLICATION_STATUSES = ("queued", "running", "published", "failed")
_DOC_TYPES = ("report",)

_TABLES = ("project_links", "publications")
_LINK_API_UPDATABLE = ("status", "display_name", "last_check_at", "last_check_error", "updated_at")
_PUBLICATION_WORKER_UPDATABLE = (
    "status",
    "attempts",
    "run_after",
    "external_id",
    "external_url",
    "error_code",
    "updated_at",
)
_GRANTS: dict[str, dict[str, str]] = {
    "project_links": {
        "basho_api": f"SELECT, INSERT, UPDATE ({', '.join(_LINK_API_UPDATABLE)})",
        "basho_worker": "SELECT",
    },
    "publications": {
        "basho_api": "SELECT, INSERT",
        "basho_worker": f"SELECT, INSERT, UPDATE ({', '.join(_PUBLICATION_WORKER_UPDATABLE)})",
    },
}
_TENANT_EXPR = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def _in_list(values: Sequence[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE project_links (
            id                uuid        PRIMARY KEY,
            tenant_id         uuid        NOT NULL,
            project_id        uuid        NOT NULL,
            kind              text        NOT NULL,
            url               text        NOT NULL,
            external_id       text        NOT NULL,
            display_name      text        NOT NULL,
            status            text        NOT NULL DEFAULT 'active',
            last_check_at     timestamptz,
            last_check_error  text,
            created_by        uuid        NOT NULL,
            created_at        timestamptz NOT NULL DEFAULT now(),
            updated_at        timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_project_links_kind CHECK (kind IN ({_in_list(_LINK_KINDS)})),
            CONSTRAINT ck_project_links_status CHECK (status IN ({_in_list(_LINK_STATUSES)})),
            CONSTRAINT uq_project_links_tenant_id UNIQUE (tenant_id, id),
            CONSTRAINT uq_project_links_target UNIQUE (tenant_id, project_id, kind, external_id)
        )
        """
    )
    op.execute("CREATE INDEX ix_project_links_project ON project_links (tenant_id, project_id)")
    op.execute(
        f"""
        CREATE TABLE publications (
            id                 uuid        PRIMARY KEY,
            tenant_id          uuid        NOT NULL,
            project_id         uuid        NOT NULL,
            link_id            uuid        NOT NULL,
            artifact_event_id  uuid        NOT NULL,
            doc_type           text        NOT NULL DEFAULT 'report',
            title              text        NOT NULL,
            status             text        NOT NULL DEFAULT 'queued',
            attempts           integer     NOT NULL DEFAULT 0,
            run_after          timestamptz NOT NULL DEFAULT now(),
            external_id        text,
            external_url       text,
            error_code         text,
            created_at         timestamptz NOT NULL DEFAULT now(),
            updated_at         timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_publications_status CHECK (status IN ({_in_list(_PUBLICATION_STATUSES)})),
            CONSTRAINT ck_publications_doc_type CHECK (doc_type IN ({_in_list(_DOC_TYPES)})),
            CONSTRAINT ck_publications_attempts CHECK (attempts >= 0),
            CONSTRAINT ck_publications_published_has_ref
                CHECK (status <> 'published' OR external_id IS NOT NULL),
            CONSTRAINT uq_publications_target
                UNIQUE (tenant_id, link_id, artifact_event_id, doc_type),
            CONSTRAINT fk_publications_link_same_tenant
                FOREIGN KEY (tenant_id, link_id) REFERENCES project_links (tenant_id, id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_publications_queue ON publications (run_after, created_at) "
        "WHERE status IN ('queued', 'running')"
    )
    op.execute("CREATE INDEX ix_publications_project ON publications (tenant_id, project_id)")
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


def downgrade() -> None:
    # Estado operacional (não é evidência): recusa só se houver publicação em andamento.
    op.execute("ALTER TABLE publications NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE project_links NO FORCE ROW LEVEL SECURITY")
    op.execute("DROP TABLE publications")
    op.execute("DROP TABLE project_links")
