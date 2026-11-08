"""Worker de publicação: consome `publications` e escreve no Drive/Notion (ADR-0010).

Passo determinístico depois do Checker, não uma tool do agente: o agente nunca recebe ação
externa de escrita nem tool `formal`. Cada publicação é reservada com ``FOR UPDATE SKIP LOCKED``,
processada **sem transação aberta** (chamada externa) e gravada com o resultado. Antes de criar,
os adaptadores procuram o documento no destino, então repetir depois de falha não duplica.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from basho.db import tenant_session
from basho.logging import get_logger
from basho.projects import ProjectService
from basho.publishing.clients.errors import ProviderError
from basho.publishing.contracts import LinkStatus, PublicationStatus
from basho.publishing.destinations import IntegrationRegistry
from basho.publishing.links import LinkKind
from basho.publishing.models import ProjectLinkRow, PublicationRow
from basho.publishing.render import render_report
from basho.publishing.service import PUBLISHABLE

logger = get_logger(__name__)

Factory = async_sessionmaker[AsyncSession]
MAX_ATTEMPTS = 5
BACKOFF_BASE_SECONDS = 5
BACKOFF_MAX_SECONDS = 300
STALE_RUNNING = timedelta(minutes=10)
LINK_UNAVAILABLE = "link_unavailable"
ARTIFACT_NOT_PUBLISHABLE = "artifact_not_publishable"
DESTINATION_NOT_CONFIGURED = "not_configured"
UNEXPECTED_ERROR = "unexpected_error"


def _utcnow() -> datetime:
    return datetime.now(UTC)


def retry_delay(attempts: int) -> timedelta:
    seconds = BACKOFF_BASE_SECONDS * 2 ** max(attempts - 1, 0)
    return timedelta(seconds=min(seconds, BACKOFF_MAX_SECONDS))


class PublicationWorker:
    def __init__(
        self,
        *,
        factory: Factory,
        registry: IntegrationRegistry,
        tenant_id: UUID,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._factory = factory
        self._registry = registry
        self._tenant_id = tenant_id
        self._clock = clock

    async def _claim(self) -> PublicationRow | None:
        now = self._clock()
        async with tenant_session(self._factory, self._tenant_id) as session:
            statement = (
                select(PublicationRow)
                .where(
                    PublicationRow.tenant_id == self._tenant_id,
                    or_(
                        and_(
                            PublicationRow.status == PublicationStatus.QUEUED.value,
                            PublicationRow.run_after <= now,
                        ),
                        and_(
                            PublicationRow.status == PublicationStatus.RUNNING.value,
                            PublicationRow.updated_at < now - STALE_RUNNING,
                        ),
                    ),
                )
                .order_by(PublicationRow.created_at, PublicationRow.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            row = (await session.execute(statement)).scalar_one_or_none()
            if row is None:
                return None
            attempts = row.attempts + 1
            await session.execute(
                update(PublicationRow)
                .where(PublicationRow.tenant_id == self._tenant_id, PublicationRow.id == row.id)
                .values(status=PublicationStatus.RUNNING.value, attempts=attempts, updated_at=now)
                .execution_options(synchronize_session=False)
            )
            session.expunge(row)
            row.attempts = attempts  # fora da sessão: o contador do banco já foi gravado acima
            return row

    async def _save(self, publication_id: UUID, **values: object) -> None:
        async with tenant_session(self._factory, self._tenant_id) as session:
            await session.execute(
                update(PublicationRow)
                .where(
                    PublicationRow.tenant_id == self._tenant_id,
                    PublicationRow.id == publication_id,
                )
                .values(updated_at=self._clock(), **values)
            )

    async def _fail(self, row: PublicationRow, code: str, *, retryable: bool) -> None:
        if retryable and row.attempts < MAX_ATTEMPTS:
            await self._save(
                row.id,
                status=PublicationStatus.QUEUED.value,
                error_code=code,
                run_after=self._clock() + retry_delay(row.attempts),
            )
            logger.warning("publication_retry", publication_id=str(row.id), code=code)
            return
        await self._save(row.id, status=PublicationStatus.FAILED.value, error_code=code)
        logger.warning("publication_failed", publication_id=str(row.id), code=code)

    async def process_one(self) -> UUID | None:
        """Processa uma publicação liberada; `None` se a fila estiver vazia."""
        row = await self._claim()
        if row is None:
            return None
        try:
            await self._publish(row)
        except ProviderError as exc:
            await self._fail(row, exc.code.value, retryable=exc.retryable)
        except Exception as exc:  # falha explícita no registro, nunca engolida em silêncio
            logger.error("publication_crashed", error_type=type(exc).__name__)
            await self._fail(row, UNEXPECTED_ERROR, retryable=False)
        return row.id

    async def _publish(self, row: PublicationRow) -> None:
        async with tenant_session(self._factory, self._tenant_id) as session:
            link = (
                await session.execute(
                    select(ProjectLinkRow).where(
                        ProjectLinkRow.tenant_id == self._tenant_id,
                        ProjectLinkRow.id == row.link_id,
                    )
                )
            ).scalar_one_or_none()
            projects = ProjectService(session)
            project = await projects.get_project(self._tenant_id, row.project_id)
            dossier = await projects.dossier(self._tenant_id, row.project_id)
        if link is None or link.status != LinkStatus.ACTIVE.value:
            await self._fail(row, LINK_UNAVAILABLE, retryable=False)
            return
        entry = next((e for e in dossier.entries if e.artifact_id == row.artifact_event_id), None)
        if entry is None or entry.status not in PUBLISHABLE:
            # Corrigido ou reprovado depois de enfileirar: não publica versão que deixou de valer.
            await self._fail(row, ARTIFACT_NOT_PUBLISHABLE, retryable=False)
            return
        destination = self._registry.destination(LinkKind(link.kind))
        if destination is None:
            await self._fail(row, DESTINATION_NOT_CONFIGURED, retryable=False)
            return
        doc = render_report(
            entry,
            project_name=project.name,
            is_synthetic=project.is_synthetic,
            generated_at=self._clock(),
        )
        published = await destination.publish(link.external_id, doc)
        await self._save(
            row.id,
            status=PublicationStatus.PUBLISHED.value,
            external_id=published.external_id,
            external_url=published.url or None,
            error_code=None,
        )
        logger.info("publication_published", publication_id=str(row.id), kind=link.kind)
