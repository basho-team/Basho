"""Contratos do Evidence Ledger (ADR-0003).

Eventos são imutáveis: correção = novo evento com `supersedes`.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

SHA256_HEX_LENGTH = 64


class EventKind(StrEnum):
    """Tipos de fato registrados no ledger."""

    COMMIT_OBSERVED = "commit_observed"
    PULL_REQUEST_OBSERVED = "pull_request_observed"
    ISSUE_OBSERVED = "issue_observed"
    DOCUMENT_OBSERVED = "document_observed"
    """Revisão de um documento externo (Drive, Notion). Nova revisão = novo evento com
    `supersedes` apontando para a anterior; o original nunca muda (ADR-0003/0012)."""
    TECHNICAL_JUSTIFICATION = "technical_justification"
    ACTIVITY_RECORD = "activity_record"
    FORMAL_HOURS_DECLARED = "formal_hours_declared"
    EXPENSE_DECLARED = "expense_declared"
    USER_CONFIRMATION = "user_confirmation"
    USER_CORRECTION = "user_correction"
    VERIFICATION_RESULT = "verification_result"
    STATUS_CHANGED = "status_changed"


class EventSource(StrEnum):
    """Origem do fato. Só `USER` e `FORMAL_SYSTEM` podem originar dados formais."""

    GITHUB = "github"
    GOOGLE_DRIVE = "google_drive"
    NOTION = "notion"
    USER = "user"
    FORMAL_SYSTEM = "formal_system"
    AGENT = "agent"
    SYSTEM = "system"


EXTERNAL_SOURCES: tuple[EventSource, ...] = (
    EventSource.GITHUB,
    EventSource.NOTION,
    EventSource.GOOGLE_DRIVE,
)
"""Fontes externas lidas pela conexão da organização (ADR-0007/0012), na ordem de exibição."""


class SourceSummary(BaseModel):
    """O que uma fonte externa já trouxe para o projeto (só contagens e datas, sem conteúdo)."""

    model_config = ConfigDict(frozen=True)

    source: EventSource
    events: int
    documents: int
    """Documentos ou itens distintos (doc_id; para o GitHub, sha/PR)."""
    last_seen_at: datetime | None
    scopes: list[str]
    """Repositórios observados (só GitHub); pastas e databases ficam na configuração."""


FORMAL_DATA_KINDS: frozenset[EventKind] = frozenset(
    {EventKind.FORMAL_HOURS_DECLARED, EventKind.EXPENSE_DECLARED}
)
FORMAL_DATA_SOURCES: frozenset[EventSource] = frozenset(
    {EventSource.USER, EventSource.FORMAL_SYSTEM}
)


class ArtifactStatus(StrEnum):
    """Estados de artefatos formais (docs/architecture.md §5)."""

    DRAFT = "draft"
    PROPOSED = "proposed"
    VERIFIED = "verified"
    NEEDS_HUMAN = "needs_human"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_REVIEW = "needs_review"


class ActorType(StrEnum):
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"


class Actor(BaseModel):
    """Quem originou o evento. Agentes registram papel e modelo (ADR-0004)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    type: ActorType
    id: str = Field(min_length=1, description="user id, 'maker', 'checker' ou 'system'")
    model: str | None = Field(
        default=None, description="Ex.: claude-sonnet-5-5; obrigatório p/ agente"
    )


ContentHash = Annotated[
    str,
    Field(
        min_length=SHA256_HEX_LENGTH,
        max_length=SHA256_HEX_LENGTH,
        pattern=r"^[0-9a-f]+$",
    ),
]


class NewEvidenceEvent(BaseModel):
    """Entrada para `EvidenceService.append`. O serviço calcula id, hash e data."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tenant_id: UUID
    project_id: UUID
    kind: EventKind
    source: EventSource
    source_ref: str | None = Field(default=None, description="sha, PR#, issue#, doc id")
    actor: Actor
    payload: dict[str, Any]
    supersedes: UUID | None = None
    is_synthetic: bool = False


class EvidenceEvent(NewEvidenceEvent):
    """Evento persistido (somente leitura)."""

    id: UUID
    content_hash: ContentHash
    created_at: datetime
