"""Ingestão Drive/Notion → ledger (ADR-0012), com Postgres real e o role do worker."""

from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from basho.connectors.documents import DocumentIngestService
from basho.connectors.sources import DocumentSources, sync_project_documents
from basho.db import tenant_session
from basho.evidence import CorrectionPropagation, EvidenceService
from basho.evidence.contracts import (
    Actor,
    ActorType,
    EventKind,
    EventSource,
    EvidenceEvent,
    NewEvidenceEvent,
)
from document_support import DATABASE, DOC_ID, FOLDER, INJECTION, PDF_ID, FakeDrive, FakeNotion
from evidence_factories import fresh_ids

pytestmark = pytest.mark.db

Factory = async_sessionmaker[AsyncSession]
MAKER = Actor(type=ActorType.AGENT, id="maker", model="test-maker-model")


async def _documents(factory: Factory, tenant_id: UUID, project_id: UUID) -> list[EvidenceEvent]:
    async with tenant_session(factory, tenant_id) as session:
        return await EvidenceService(session).query(
            tenant_id, project_id=project_id, kinds=[EventKind.DOCUMENT_OBSERVED]
        )


async def _drive_sync(factory: Factory, tenant_id: UUID, project_id: UUID, fake: FakeDrive):  # type: ignore[no-untyped-def]
    snapshots = await fake.client().snapshots(FOLDER)
    async with tenant_session(factory, tenant_id) as session:
        return await DocumentIngestService(session, EventSource.GOOGLE_DRIVE).sync(
            tenant_id, project_id, FOLDER.folder_id, snapshots, is_synthetic=True
        )


async def test_drive_sync_records_each_revision_once(worker_session_factory: Factory) -> None:
    # Arrange
    tenant_id, project_id = fresh_ids()
    fake = FakeDrive()

    # Act
    first = await _drive_sync(worker_session_factory, tenant_id, project_id, fake)
    second = await _drive_sync(worker_session_factory, tenant_id, project_id, fake)
    events = await _documents(worker_session_factory, tenant_id, project_id)

    # Assert
    assert (first.created, first.skipped) == (2, 0)
    assert (second.created, second.skipped) == (0, 2)
    assert sorted(e.source_ref for e in events if e.source_ref) == [f"{DOC_ID}@7", f"{PDF_ID}@3"]
    assert all(e.source is EventSource.GOOGLE_DRIVE and e.is_synthetic for e in events)
    doc = next(e for e in events if e.source_ref == f"{DOC_ID}@7")
    assert INJECTION in doc.payload["text"]  # texto externo guardado como dado
    assert doc.payload["content_sha256"] is not None
    assert doc.actor.id == "google_drive-connector"


async def test_new_revision_supersedes_previous_and_flags_citing_report(
    worker_session_factory: Factory,
) -> None:
    # Arrange: revisão 7 do documento citada por um registro do Maker
    tenant_id, project_id = fresh_ids()
    fake = FakeDrive()
    await _drive_sync(worker_session_factory, tenant_id, project_id, fake)
    original = next(
        e
        for e in await _documents(worker_session_factory, tenant_id, project_id)
        if e.source_ref == f"{DOC_ID}@7"
    )
    draft = {
        "summary": "rascunho sintético",
        "claims": [{"text": "afirmação", "evidence_ids": [str(original.id)]}],
        "formal_hours_event_ids": [],
        "missing": [],
    }
    async with tenant_session(worker_session_factory, tenant_id) as session:
        artifact = await EvidenceService(session).append(
            NewEvidenceEvent(
                tenant_id=tenant_id,
                project_id=project_id,
                kind=EventKind.ACTIVITY_RECORD,
                source=EventSource.AGENT,
                actor=MAKER,
                payload={"draft": draft},
                is_synthetic=True,
            )
        )

    # Act: o documento muda no Drive (versão 8)
    fake.doc_version = "8"
    fake.doc_text = "Resultado revisado: p95 caiu 4% com cache aquecido."
    result = await _drive_sync(worker_session_factory, tenant_id, project_id, fake)

    # Assert
    assert (result.created, result.superseded, result.marked_for_review) == (1, 1, 1)
    events = await _documents(worker_session_factory, tenant_id, project_id)
    newer = next(e for e in events if e.source_ref == f"{DOC_ID}@8")
    assert newer.supersedes == original.id
    still_there = next(e for e in events if e.id == original.id)
    assert still_there.payload == original.payload  # original intacto (ADR-0003)
    async with tenant_session(worker_session_factory, tenant_id) as session:
        pending = await CorrectionPropagation(session).pending_reviews(tenant_id, project_id)
    assert [p.artifact_event_id for p in pending] == [artifact.id]


async def test_notion_sync_through_sources_is_idempotent(worker_session_factory: Factory) -> None:
    # Arrange
    tenant_id, project_id = fresh_ids()
    sources = DocumentSources(notion=FakeNotion().client(), notion_refs={project_id: [DATABASE]})

    # Act
    for _ in range(2):
        report = await sync_project_documents(
            sources,
            worker_session_factory,
            tenant_id,
            project_id,
            since=None,
            is_synthetic=True,
        )

    # Assert
    result = report.results[f"notion:{DATABASE.scope}"]
    assert (result.created, result.skipped) == (0, 2)
    events = await _documents(worker_session_factory, tenant_id, project_id)
    assert len(events) == 2
    assert all(e.source is EventSource.NOTION for e in events)
    assert {e.payload["title"] for e in events} == {"Diário do experimento", "Notas de bench"}
