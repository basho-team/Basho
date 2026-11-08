"""Ingestão de documentos externos (Drive, Notion) no Evidence Ledger (ADR-0003/0006/0010).

Cada **revisão** de documento vira um evento `document_observed` com `source_ref` estável
(`<doc_id>@<revisão>`). Reexecutar não duplica. Quando aparece uma revisão nova de um documento
já registrado, o evento novo leva `supersedes` = revisão anterior e a propagação (#11) marca
`needs_review` em todo relatório que citava a revisão antiga: evidência substituída nunca
continua tratada como confirmada. O original fica intacto no ledger.

O texto é dado não confiável: vai no payload (truncado) e só chega ao modelo em
`untrusted_data`. O hash SHA-256 do conteúdo lido fica no payload para provar qual versão foi
observada. Nada de e-mail ou nome de autor (LGPD).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from basho.evidence import MAX_PAGE_SIZE, EvidenceService
from basho.evidence.contracts import (
    Actor,
    ActorType,
    EventKind,
    EventSource,
    EvidenceEvent,
    NewEvidenceEvent,
)
from basho.evidence.propagation import CorrectionPropagation

MAX_TEXT_CHARS = 20_000
"""Texto de documento é truncado no payload: dado externo sem limite vira risco."""
_HISTORY_PAGE = MAX_PAGE_SIZE


@dataclass(frozen=True, slots=True)
class DocumentSnapshot:
    """Uma revisão lida de uma fonte. `text` é o conteúdo integral lido (antes de truncar)."""

    doc_id: str
    revision: str
    title: str
    url: str | None
    mime_type: str | None
    modified_at: str | None
    text: str | None
    """`None` quando o formato não é lido como texto (PDF, imagem): só metadados entram."""
    checksum: str | None = None
    """Checksum fornecido pela fonte (ex.: `md5Checksum` do Drive) quando não há texto."""

    @property
    def source_ref(self) -> str:
        return f"{self.doc_id}@{self.revision}"


@dataclass(frozen=True, slots=True)
class DocumentIngestResult:
    created: int
    skipped: int
    superseded: int
    """Revisões novas que substituíram uma anterior (e dispararam a propagação)."""
    marked_for_review: int


def document_payload(snapshot: DocumentSnapshot) -> dict[str, object]:
    body = snapshot.text
    return {
        "doc_id": snapshot.doc_id,
        "revision": snapshot.revision,
        "title": snapshot.title[:500],
        "url": snapshot.url,
        "mime_type": snapshot.mime_type,
        "modified_at": snapshot.modified_at,
        "text": None if body is None else body[:MAX_TEXT_CHARS],
        "text_truncated": body is not None and len(body) > MAX_TEXT_CHARS,
        "content_sha256": None
        if body is None
        else hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "source_checksum": snapshot.checksum,
    }


class DocumentIngestService:
    """Grava revisões de documentos de uma origem. Roda dentro de `tenant_session`."""

    def __init__(self, session: AsyncSession, source: EventSource) -> None:
        if source not in (EventSource.GOOGLE_DRIVE, EventSource.NOTION):
            msg = "origem de documento não suportada"
            raise ValueError(msg)
        self._session = session
        self._source = source
        self._ledger = EvidenceService(session)
        self._propagation = CorrectionPropagation(session)
        self._actor = Actor(type=ActorType.SYSTEM, id=f"{source.value}-connector")

    async def sync(
        self,
        tenant_id: UUID,
        project_id: UUID,
        scope: str,
        snapshots: list[DocumentSnapshot],
        *,
        is_synthetic: bool = False,
    ) -> DocumentIngestResult:
        """`scope` identifica o conjunto (pasta, database) só para o lock de concorrência."""
        await self._lock(tenant_id, project_id, scope)
        unique = list({s.source_ref: s for s in snapshots}.values())
        known = await self._ledger.existing_source_refs(
            tenant_id, project_id, self._source, (s.source_ref for s in unique)
        )
        latest = await self._latest_by_doc(tenant_id, project_id)
        created = superseded = marked = 0
        for snapshot in sorted(unique, key=lambda s: (s.modified_at or "", s.revision)):
            if snapshot.source_ref in known:
                continue
            previous = latest.get(snapshot.doc_id)
            event = await self._ledger.append(
                NewEvidenceEvent(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    kind=EventKind.DOCUMENT_OBSERVED,
                    source=self._source,
                    source_ref=snapshot.source_ref,
                    actor=self._actor,
                    payload=document_payload(snapshot),
                    supersedes=None if previous is None else previous.id,
                    is_synthetic=is_synthetic,
                )
            )
            created += 1
            latest[snapshot.doc_id] = event
            if previous is not None:
                superseded += 1
                result = await self._propagation.propagate(tenant_id, event.id)
                marked += len(result.marked)
        return DocumentIngestResult(
            created=created,
            skipped=len(unique) - created,
            superseded=superseded,
            marked_for_review=marked,
        )

    async def _latest_by_doc(self, tenant_id: UUID, project_id: UUID) -> dict[str, EvidenceEvent]:
        """Revisão mais recente já registrada de cada documento desta origem."""
        latest: dict[str, EvidenceEvent] = {}
        before = None
        while True:
            page = await self._ledger.query(
                tenant_id,
                project_id=project_id,
                kinds=[EventKind.DOCUMENT_OBSERVED],
                limit=_HISTORY_PAGE,
                before=before,
            )
            for event in page:  # do mais novo ao mais antigo: o primeiro visto é o atual
                doc_id = event.payload.get("doc_id")
                if event.source is self._source and isinstance(doc_id, str):
                    latest.setdefault(doc_id, event)
            if len(page) < _HISTORY_PAGE:
                return latest
            before = (page[-1].created_at, page[-1].id)

    async def _lock(self, tenant_id: UUID, project_id: UUID, scope: str) -> None:
        key = f"{self._source.value}-ingest:{tenant_id}:{project_id}:{scope}"
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": key}
        )
