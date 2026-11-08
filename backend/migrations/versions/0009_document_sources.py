"""Amplia os CHECKs do ledger para documentos do Google Drive e do Notion (ADR-0012).

Só troca as constraints `ck_evidence_events_kind`/`ck_evidence_events_source`: nenhuma linha é
alterada (ADR-0003). O downgrade falha se já houver eventos com os valores novos, de propósito:
apagar evidência para voltar o schema não é opção.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-08
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Valores congelados nesta migração (espelham EventKind/EventSource em 2026-11-08).
_PREVIOUS_KINDS = (
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
_PREVIOUS_SOURCES = ("github", "user", "formal_system", "agent", "system")
_KINDS = (*_PREVIOUS_KINDS, "document_observed")
_SOURCES = (*_PREVIOUS_SOURCES, "google_drive", "notion")


def _in_list(values: Sequence[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _replace_checks(kinds: Sequence[str], sources: Sequence[str]) -> None:
    op.execute(
        f"""
        ALTER TABLE evidence_events
            DROP CONSTRAINT ck_evidence_events_kind,
            DROP CONSTRAINT ck_evidence_events_source,
            ADD CONSTRAINT ck_evidence_events_kind CHECK (kind IN ({_in_list(kinds)})),
            ADD CONSTRAINT ck_evidence_events_source CHECK (source IN ({_in_list(sources)}))
        """
    )


def upgrade() -> None:
    _replace_checks(_KINDS, _SOURCES)


def downgrade() -> None:
    _replace_checks(_PREVIOUS_KINDS, _PREVIOUS_SOURCES)
