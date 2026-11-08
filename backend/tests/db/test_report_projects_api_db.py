"""Rotas por projeto/período com Postgres real: rascunho automático, lista, consolidação."""

from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine import URL

from basho.config import Settings
from basho.db import tenant_session
from basho.evidence import EvidenceService
from basho.evidence.contracts import EventKind
from basho.main import create_app
from conftest import VALID_ENV
from evidence_factories import make_event

pytestmark = pytest.mark.db

IDENTITY_SECRET = "test-identity-secret-synthetic-projects-01"  # noqa: S105 -- sintético
ANA = UUID("33333333-3333-4333-8333-333333333333")
CARLA = UUID("55555555-5555-4555-8555-555555555555")
Q = {"start": "2026-10-01", "end": "2026-10-31"}


def _who(user: UUID, role: str) -> dict[str, str]:
    return {
        "X-Basho-User-Id": str(user),
        "X-Basho-Role": role,
        "X-Basho-Identity-Secret": IDENTITY_SECRET,
    }


ANA_H, CARLA_H = _who(ANA, "researcher"), _who(CARLA, "manager")


def _settings(url: URL, tenant_id: UUID) -> Settings:
    env: dict[str, str | None] = {name.lower(): value for name, value in VALID_ENV.items()}
    env["database_url"] = url.render_as_string(hide_password=False)
    env["tenant_id"] = str(tenant_id)
    env["reviewer_identity_secret"] = IDENTITY_SECRET
    return Settings.model_validate(env)


@pytest.fixture
def tenant_id() -> UUID:
    return uuid4()


@pytest.fixture
async def app(api_url: URL, tenant_id: UUID) -> AsyncIterator[FastAPI]:
    created = create_app(_settings(api_url, tenant_id))
    async with created.router.lifespan_context(created):
        yield created


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


async def _evidence(app: FastAPI, tenant_id: UUID, project: UUID, **overrides: Any) -> UUID:
    async with tenant_session(app.state.session_factory, tenant_id) as session:
        event = await EvidenceService(session).append(
            make_event(tenant_id=tenant_id, project_id=project, **overrides)
        )
    return event.id


async def test_auto_draft_cites_own_evidence_once_and_feeds_consolidation(
    app: FastAPI, client: AsyncClient, tenant_id: UUID
) -> None:
    project = uuid4()
    draft_url = f"/api/v1/projects/{project}/reports/auto-draft"
    assert (await client.post(draft_url, params=Q, headers=ANA_H)).status_code == 404
    pr = await _evidence(
        app,
        tenant_id,
        project,
        kind=EventKind.PULL_REQUEST_OBSERVED,
        payload={
            "title": "PR #42",
            "description": "Quantização int8 dinâmica.",
            "researcher_id": str(ANA),
        },
    )
    await _evidence(
        app,
        tenant_id,
        project,
        kind=EventKind.COMMIT_OBSERVED,
        payload={
            "title": "b101",
            "description": "Calibração de outra pessoa.",
            "researcher_id": str(uuid4()),
        },
    )

    first = await client.post(draft_url, params=Q, headers=ANA_H)
    assert first.status_code == 201, first.text
    version = first.json()["version"]
    cited = {e for c in version["draft"]["claims"] for e in c["evidence_ids"]}
    assert cited == {str(pr)}
    fields = {m["field"] for m in version["draft"]["missing"]}
    assert {"experiment_outcomes", "formal_hours"} <= fields
    again = await client.post(draft_url, params=Q, headers=ANA_H)
    assert again.json()["version"]["id"] == version["id"]

    listed = (
        await client.get(f"/api/v1/projects/{project}/reports", params=Q, headers=CARLA_H)
    ).json()
    assert [r["version"]["id"] for r in listed] == [version["id"]]
    cons = (
        await client.get(f"/api/v1/projects/{project}/consolidation", params=Q, headers=CARLA_H)
    ).json()
    assert cons["consolidation"]["reports"][0]["researcher"]["state"] == "awaiting_review"
    assert "Consolidação operacional" in cons["summary_markdown"]


async def test_only_researcher_drafts_and_reads_need_identity(
    app: FastAPI, client: AsyncClient, tenant_id: UUID
) -> None:
    project = uuid4()
    await _evidence(
        app,
        tenant_id,
        project,
        kind=EventKind.ACTIVITY_RECORD,
        payload={
            "title": "Atividade",
            "description": "Atividade registrada.",
            "researcher_id": str(CARLA),
        },
    )
    draft_url = f"/api/v1/projects/{project}/reports/auto-draft"
    assert (await client.post(draft_url, params=Q, headers=CARLA_H)).status_code == 403
    for path in ("reports", "consolidation"):
        url = f"/api/v1/projects/{project}/{path}"
        assert (await client.get(url, params=Q)).status_code == 401


async def test_empty_period_returns_empty(client: AsyncClient) -> None:
    project = uuid4()
    url = f"/api/v1/projects/{project}"
    assert (await client.get(f"{url}/reports", params=Q, headers=CARLA_H)).json() == []
    empty = (await client.get(f"{url}/consolidation", params=Q, headers=CARLA_H)).json()
    assert empty == {"consolidation": None, "summary_markdown": None, "needs_review": []}


async def test_other_tenant_sees_nothing(
    app: FastAPI, client: AsyncClient, tenant_id: UUID, api_url: URL
) -> None:
    project = uuid4()
    await _evidence(
        app,
        tenant_id,
        project,
        kind=EventKind.PULL_REQUEST_OBSERVED,
        payload={"title": "PR", "description": "Trabalho do tenant A.", "researcher_id": str(ANA)},
    )
    assert (
        await client.post(f"/api/v1/projects/{project}/reports/auto-draft", params=Q, headers=ANA_H)
    ).status_code == 201
    other = create_app(_settings(api_url, uuid4()))
    async with (
        other.router.lifespan_context(other),
        AsyncClient(transport=ASGITransport(app=other), base_url="http://test") as http,
    ):
        listed = await http.get(f"/api/v1/projects/{project}/reports", params=Q, headers=CARLA_H)
        assert listed.json() == []
