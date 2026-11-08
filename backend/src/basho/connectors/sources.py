"""Fontes de documentos por projeto (Drive, Notion) e a sincronização antes do Maker (ADR-0010).

O mapa projeto → pasta/database vem da configuração (`GOOGLE_DRIVE_PROJECT_FOLDERS`,
`NOTION_PROJECT_SOURCES`), nunca do modelo. Cada fonte sincroniza numa transação curta própria:
uma falha não desfaz o que outra fonte já gravou, e o erro volta com código estável.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from basho.config import Settings
from basho.connectors.documents import DocumentIngestResult, DocumentIngestService
from basho.connectors.google_drive import DriveCredentials, FolderRef, GoogleDriveClient
from basho.connectors.http import ConnectorError
from basho.connectors.notion import NotionClient, NotionRef
from basho.db import tenant_session
from basho.evidence.contracts import EventSource
from basho.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class DocumentSources:
    drive: GoogleDriveClient | None = None
    drive_folders: Mapping[UUID, Sequence[FolderRef]] = field(default_factory=dict)
    notion: NotionClient | None = None
    notion_refs: Mapping[UUID, Sequence[NotionRef]] = field(default_factory=dict)

    @property
    def configured(self) -> bool:
        return bool(
            (self.drive is not None and self.drive_folders)
            or (self.notion is not None and self.notion_refs)
        )


def document_sources(settings: Settings, http_client: httpx.AsyncClient) -> DocumentSources:
    """Monta só o que está completo. `FolderRef`/`NotionRef` validam os IDs (fail fast)."""
    drive = None
    folders: dict[UUID, list[FolderRef]] = {}
    secret, refresh = settings.google_drive_client_secret, settings.google_drive_refresh_token
    if settings.google_drive_client_id and secret is not None and refresh is not None:
        folders = {
            project: [FolderRef(item) for item in items]
            for project, items in settings.google_drive_project_folders.items()
        }
        if folders:
            drive = GoogleDriveClient(
                credentials=DriveCredentials(settings.google_drive_client_id, secret, refresh),
                http_client=http_client,
            )
    notion = None
    refs: dict[UUID, list[NotionRef]] = {}
    if settings.notion_token is not None:
        refs = {
            project: [NotionRef.parse(item) for item in items]
            for project, items in settings.notion_project_sources.items()
        }
        if refs:
            notion = NotionClient(token=settings.notion_token, http_client=http_client)
    return DocumentSources(drive, folders if drive else {}, notion, refs if notion else {})


@dataclass(frozen=True, slots=True)
class DocumentSyncReport:
    results: Mapping[str, DocumentIngestResult]


async def sync_project_documents(
    sources: DocumentSources,
    factory: async_sessionmaker[AsyncSession],
    tenant_id: UUID,
    project_id: UUID,
    *,
    since: datetime | None,
    is_synthetic: bool,
) -> DocumentSyncReport:
    """Lê cada pasta/database do projeto e grava as revisões novas. Sobe `ConnectorError`."""
    results: dict[str, DocumentIngestResult] = {}
    if sources.drive is not None:
        for folder in sources.drive_folders.get(project_id, ()):
            snapshots = await sources.drive.snapshots(folder, since=since)
            async with tenant_session(factory, tenant_id) as session:
                results[f"google_drive:{folder.folder_id}"] = await DocumentIngestService(
                    session, EventSource.GOOGLE_DRIVE
                ).sync(
                    tenant_id,
                    project_id,
                    folder.folder_id,
                    snapshots,
                    is_synthetic=is_synthetic,
                )
    if sources.notion is not None:
        for ref in sources.notion_refs.get(project_id, ()):
            snapshots = await sources.notion.snapshots(ref, since=since)
            async with tenant_session(factory, tenant_id) as session:
                results[f"notion:{ref.scope}"] = await DocumentIngestService(
                    session, EventSource.NOTION
                ).sync(tenant_id, project_id, ref.scope, snapshots, is_synthetic=is_synthetic)
    for scope, result in results.items():
        logger.info(
            "documents_synced",
            scope=scope,
            created=result.created,
            skipped=result.skipped,
            superseded=result.superseded,
            marked_for_review=result.marked_for_review,
        )
    return DocumentSyncReport(results)


__all__ = [
    "ConnectorError",
    "DocumentSources",
    "DocumentSyncReport",
    "document_sources",
    "sync_project_documents",
]
