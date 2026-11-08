"""Resumo das fontes externas por projeto (GET /projects/{id}/sources), direto no service."""

from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from basho.db import tenant_session
from basho.evidence import EvidenceService
from basho.evidence.contracts import Actor, ActorType, EventKind, EventSource, NewEvidenceEvent
from evidence_factories import fresh_ids

pytestmark = pytest.mark.db

Factory = async_sessionmaker[AsyncSession]


def _event(
    tenant: UUID,
    project: UUID,
    source: EventSource,
    kind: EventKind,
    ref: str,
    payload: dict[str, object],
) -> NewEvidenceEvent:
    return NewEvidenceEvent(
        tenant_id=tenant,
        project_id=project,
        kind=kind,
        source=source,
        source_ref=ref,
        actor=Actor(type=ActorType.SYSTEM, id=f"{source.value}-connector"),
        payload=payload,
        is_synthetic=True,
    )


async def test_summary_counts_events_documents_and_repos_per_source(
    worker_session_factory: Factory,
) -> None:
    # Arrange: 2 commits + 1 PR do GitHub; 2 revisões do mesmo doc do Notion; nada do Drive
    tenant, project = fresh_ids()
    events = [
        _event(
            tenant,
            project,
            EventSource.GITHUB,
            EventKind.COMMIT_OBSERVED,
            "demo/repo@" + "a" * 40,
            {"sha": "a" * 40},
        ),
        _event(
            tenant,
            project,
            EventSource.GITHUB,
            EventKind.COMMIT_OBSERVED,
            "demo/repo@" + "b" * 40,
            {"sha": "b" * 40},
        ),
        _event(
            tenant,
            project,
            EventSource.GITHUB,
            EventKind.PULL_REQUEST_OBSERVED,
            "demo/repo#7",
            {"number": 7},
        ),
        _event(
            tenant,
            project,
            EventSource.NOTION,
            EventKind.DOCUMENT_OBSERVED,
            "doc1@r1",
            {"doc_id": "doc1"},
        ),
        _event(
            tenant,
            project,
            EventSource.NOTION,
            EventKind.DOCUMENT_OBSERVED,
            "doc1@r2",
            {"doc_id": "doc1"},
        ),
    ]
    async with tenant_session(worker_session_factory, tenant) as session:
        ledger = EvidenceService(session)
        for event in events:
            await ledger.append(event)

    # Act
    async with tenant_session(worker_session_factory, tenant) as session:
        summary = await EvidenceService(session).source_summary(tenant, project)

    # Assert: sempre as três fontes, na ordem de exibição
    by_source = {item.source: item for item in summary}
    assert [item.source for item in summary] == [
        EventSource.GITHUB,
        EventSource.NOTION,
        EventSource.GOOGLE_DRIVE,
    ]
    github = by_source[EventSource.GITHUB]
    assert (github.events, github.documents, github.scopes) == (3, 3, ["demo/repo"])
    notion = by_source[EventSource.NOTION]
    assert (notion.events, notion.documents) == (2, 1)
    assert notion.last_seen_at is not None
    drive = by_source[EventSource.GOOGLE_DRIVE]
    assert (drive.events, drive.documents, drive.last_seen_at) == (0, 0, None)
