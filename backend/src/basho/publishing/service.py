"""Links autorizados e fila de publicação (ADR-0010). Roda dentro de `tenant_session`.

A autorização do tenant para ação externa rotineira (ADR-0005) é o cadastro do link por um
gerente. Publicar = enfileirar (artefato verificado por destino ativo) de forma idempotente; quem
escreve no Drive/Notion é o worker.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from basho.evidence.contracts import ArtifactStatus
from basho.projects import ProjectService
from basho.publishing.contracts import LinkOut, LinkStatus, PublicationOut, PublicationStatus
from basho.publishing.links import LinkKind, ParsedLink
from basho.publishing.models import ProjectLinkRow, PublicationRow
from basho.publishing.render import document_title

PUBLISHABLE = frozenset({ArtifactStatus.VERIFIED, ArtifactStatus.APPROVED})
DESTINATION_KINDS = (LinkKind.DRIVE_FOLDER.value, LinkKind.NOTION_PAGE.value)


def link_out(row: ProjectLinkRow) -> LinkOut:
    return LinkOut(
        id=row.id,
        project_id=row.project_id,
        kind=LinkKind(row.kind),
        url=row.url,
        display_name=row.display_name,
        status=LinkStatus(row.status),
        last_check_at=row.last_check_at,
        created_at=row.created_at,
    )


def publication_out(row: PublicationRow, link_kind: str | None) -> PublicationOut:
    return PublicationOut(
        id=row.id,
        project_id=row.project_id,
        link_id=row.link_id,
        link_kind=LinkKind(link_kind) if link_kind else None,
        artifact_id=row.artifact_event_id,
        title=row.title,
        status=PublicationStatus(row.status),
        attempts=row.attempts,
        external_url=row.external_url,
        error_code=row.error_code,
        updated_at=row.updated_at,
    )


class PublishingService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_link(
        self,
        tenant_id: UUID,
        project_id: UUID,
        parsed: ParsedLink,
        *,
        display_name: str,
        created_by: UUID,
    ) -> LinkOut:
        """Cadastra (ou reativa) o link já verificado; repetir o mesmo link não duplica."""
        now = datetime.now(UTC)
        statement = (
            pg_insert(ProjectLinkRow)
            .values(
                id=uuid4(),
                tenant_id=tenant_id,
                project_id=project_id,
                kind=parsed.kind.value,
                url=parsed.url,
                external_id=parsed.external_id,
                display_name=display_name,
                status=LinkStatus.ACTIVE.value,
                last_check_at=now,
                created_by=created_by,
            )
            .on_conflict_do_update(
                constraint="uq_project_links_target",
                set_={
                    "status": LinkStatus.ACTIVE.value,
                    "display_name": display_name,
                    "last_check_at": now,
                    "last_check_error": None,
                    "updated_at": now,
                },
            )
            .returning(ProjectLinkRow)
        )
        row = (await self._session.execute(statement)).scalar_one()
        return link_out(row)

    async def list_links(
        self, tenant_id: UUID, project_id: UUID, *, active_only: bool = False
    ) -> list[LinkOut]:
        statement = (
            select(ProjectLinkRow)
            .where(ProjectLinkRow.tenant_id == tenant_id, ProjectLinkRow.project_id == project_id)
            .order_by(ProjectLinkRow.created_at, ProjectLinkRow.id)
        )
        if active_only:
            statement = statement.where(ProjectLinkRow.status == LinkStatus.ACTIVE.value)
        return [link_out(row) for row in (await self._session.execute(statement)).scalars()]

    async def revoke_link(self, tenant_id: UUID, project_id: UUID, link_id: UUID) -> LinkOut | None:
        statement = (
            update(ProjectLinkRow)
            .where(
                ProjectLinkRow.tenant_id == tenant_id,
                ProjectLinkRow.project_id == project_id,
                ProjectLinkRow.id == link_id,
            )
            .values(status=LinkStatus.REVOKED.value, updated_at=func.now())
            .returning(ProjectLinkRow)
        )
        row = (await self._session.execute(statement)).scalar_one_or_none()
        return link_out(row) if row is not None else None

    async def github_repo(self, tenant_id: UUID, project_id: UUID) -> str | None:
        """Repositório (`owner/name`) do link GitHub ativo mais recente do projeto."""
        statement = (
            select(ProjectLinkRow.external_id)
            .where(
                ProjectLinkRow.tenant_id == tenant_id,
                ProjectLinkRow.project_id == project_id,
                ProjectLinkRow.kind == LinkKind.GITHUB_REPO.value,
                ProjectLinkRow.status == LinkStatus.ACTIVE.value,
            )
            .order_by(ProjectLinkRow.created_at.desc())
            .limit(1)
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def enqueue(self, tenant_id: UUID, project_id: UUID) -> int:
        """Enfileira artefato verificado por destino ativo; devolve quantos entraram agora."""
        links = [
            link
            for link in await self.list_links(tenant_id, project_id, active_only=True)
            if link.kind.value in DESTINATION_KINDS
        ]
        if not links:
            return 0
        dossier = await ProjectService(self._session).dossier(tenant_id, project_id)
        rows = [
            {
                "id": uuid4(),
                "tenant_id": tenant_id,
                "project_id": project_id,
                "link_id": link.id,
                "artifact_event_id": entry.artifact_id,
                "doc_type": "report",
                "title": document_title(entry.title, entry.artifact_id),
            }
            for entry in dossier.entries
            if entry.status in PUBLISHABLE
            for link in links
        ]
        if not rows:
            return 0
        statement = (
            pg_insert(PublicationRow)
            .values(rows)
            .on_conflict_do_nothing(constraint="uq_publications_target")
            .returning(PublicationRow.id)
        )
        return len((await self._session.execute(statement)).all())

    async def list_publications(self, tenant_id: UUID, project_id: UUID) -> list[PublicationOut]:
        statement = (
            select(PublicationRow, ProjectLinkRow.kind)
            .join(
                ProjectLinkRow,
                (ProjectLinkRow.tenant_id == PublicationRow.tenant_id)
                & (ProjectLinkRow.id == PublicationRow.link_id),
                isouter=True,
            )
            .where(PublicationRow.tenant_id == tenant_id, PublicationRow.project_id == project_id)
            .order_by(PublicationRow.created_at.desc(), PublicationRow.id)
        )
        return [
            publication_out(row, kind) for row, kind in (await self._session.execute(statement))
        ]
