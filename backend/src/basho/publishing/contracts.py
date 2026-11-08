"""Contratos HTTP de links autorizados e publicações (ADR-0010; espelhados em docs/contracts.md)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from basho.publishing.links import MAX_URL_LENGTH, LinkKind


class LinkStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"


class PublicationStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PUBLISHED = "published"
    FAILED = "failed"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class LinkIn(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    url: str = Field(min_length=8, max_length=MAX_URL_LENGTH)


class LinkOut(_Frozen):
    id: UUID
    project_id: UUID
    kind: LinkKind
    url: str
    display_name: str
    status: LinkStatus
    last_check_at: datetime | None
    created_at: datetime


class PublicationOut(_Frozen):
    id: UUID
    project_id: UUID
    link_id: UUID
    link_kind: LinkKind | None
    artifact_id: UUID
    title: str
    status: PublicationStatus
    attempts: int
    external_url: str | None
    error_code: str | None
    updated_at: datetime


class PublicationsOut(_Frozen):
    queued: int = Field(description="Publicações novas enfileiradas por esta chamada")
    items: tuple[PublicationOut, ...]


class IntegrationsConfigOut(_Frozen):
    drive: bool
    notion: bool
    github: bool
    google_service_account_email: str | None = Field(
        description="Conta com quem o usuário compartilha a pasta do Drive (papel Editor)"
    )


class LinkErrorOut(_Frozen):
    detail: str
    code: str
