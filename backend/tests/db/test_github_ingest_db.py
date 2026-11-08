"""Ingestão GitHub → ledger (#7): eventos criados, idempotência e texto externo como dado."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from basho.connectors.github import GithubIngestService
from basho.connectors.github.ingest import commit_ref, pull_request_ref
from basho.db import tenant_session
from basho.evidence import EvidenceService
from basho.evidence.contracts import EventKind, EventSource
from evidence_factories import fresh_ids
from github_support import INJECTION, REPO, FakeGithub

pytestmark = pytest.mark.db

Factory = async_sessionmaker[AsyncSession]


async def test_sync_records_commits_and_pull_requests_once(
    worker_session_factory: Factory,
) -> None:
    # Arrange
    tenant_id, project_id = fresh_ids()
    fake = FakeGithub()

    # Act: duas execuções seguidas
    async with tenant_session(worker_session_factory, tenant_id) as session:
        first = await GithubIngestService(session, fake.client()).sync(
            tenant_id, project_id, REPO, is_synthetic=True
        )
    async with tenant_session(worker_session_factory, tenant_id) as session:
        second = await GithubIngestService(session, fake.client()).sync(
            tenant_id, project_id, REPO, is_synthetic=True
        )
    async with tenant_session(worker_session_factory, tenant_id) as session:
        events = await EvidenceService(session).query(tenant_id, project_id=project_id)

    # Assert
    assert (first.created, first.skipped) == (3, 0)
    assert (second.created, second.skipped) == (0, 3)
    assert sorted((e.kind, e.source_ref) for e in events) == sorted(
        [
            (EventKind.COMMIT_OBSERVED, commit_ref(REPO, "a" * 40)),
            (EventKind.COMMIT_OBSERVED, commit_ref(REPO, "b" * 40)),
            (EventKind.PULL_REQUEST_OBSERVED, pull_request_ref(REPO, 7)),
        ]
    )
    assert all(e.source is EventSource.GITHUB and e.is_synthetic for e in events)


async def test_ingested_payload_keeps_external_text_as_data_and_drops_email(
    worker_session_factory: Factory,
) -> None:
    # Arrange
    tenant_id, project_id = fresh_ids()

    # Act
    async with tenant_session(worker_session_factory, tenant_id) as session:
        await GithubIngestService(session, FakeGithub().client()).sync(
            tenant_id, project_id, REPO, is_synthetic=True
        )
    async with tenant_session(worker_session_factory, tenant_id) as session:
        events = await EvidenceService(session).query(
            tenant_id, project_id=project_id, kinds=[EventKind.COMMIT_OBSERVED]
        )

    # Assert
    payloads = {e.source_ref: e.payload for e in events}
    injected = payloads[commit_ref(REPO, "b" * 40)]
    assert INJECTION in injected["message"]
    assert injected["author_login"] == "ana-demo"
    assert "ana@example.com" not in str(payloads)


async def test_sync_in_other_project_is_independent(worker_session_factory: Factory) -> None:
    tenant_id, project_a = fresh_ids()
    _, project_b = fresh_ids()
    for project_id in (project_a, project_b):
        async with tenant_session(worker_session_factory, tenant_id) as session:
            result = await GithubIngestService(session, FakeGithub().client()).sync(
                tenant_id, project_id, REPO
            )
        assert result.created == 3
