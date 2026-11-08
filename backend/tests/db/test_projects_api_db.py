"""Endpoints de projetos, pendências, aprovação formal e dossiê com Postgres real (#5)."""

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from basho.config import Settings
from basho.db import tenant_session
from basho.evidence import EvidenceService
from basho.evidence.contracts import EventKind
from basho.main import create_app
from conftest import VALID_ENV
from project_db_factories import SeededArtifact, seed_artifact, seed_project

pytestmark = pytest.mark.db

IDENTITY_SECRET = "test-identity-secret-synthetic-0123456789"  # noqa: S105 -- sintético
USER = UUID("44444444-4444-4444-8444-444444444444")


def _headers(role: str) -> dict[str, str]:
    return {
        "X-Basho-User-Id": str(USER),
        "X-Basho-Role": role,
        "X-Basho-Identity-Secret": IDENTITY_SECRET,
    }


RESEARCHER = _headers("researcher")
MANAGER = _headers("manager")


def _settings(url: URL, tenant_id: UUID, secret: str | None = IDENTITY_SECRET) -> Settings:
    env: dict[str, str | None] = {name.lower(): value for name, value in VALID_ENV.items()}
    env["database_url"] = url.render_as_string(hide_password=False)
    env["tenant_id"] = str(tenant_id)
    env["reviewer_identity_secret"] = secret
    return Settings.model_validate(env)


@pytest.fixture
def tenant_id() -> UUID:
    return uuid4()


@pytest.fixture
async def app(api_url: URL, tenant_id: UUID) -> AsyncIterator[FastAPI]:
    created = create_app_for(api_url, tenant_id)
    async with created.router.lifespan_context(created):
        yield created


def create_app_for(url: URL, tenant_id: UUID, secret: str | None = IDENTITY_SECRET) -> FastAPI:
    return create_app(_settings(url, tenant_id, secret))


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


Seed = Callable[..., Awaitable[tuple[UUID, SeededArtifact]]]


@pytest.fixture
def seed(app: FastAPI, tenant_id: UUID) -> Seed:
    """Projeto + artefato do Maker + veredito, no tenant da app."""

    async def _seed(status: str | None = "verified", *, with_missing: bool = False) -> Any:
        async with tenant_session(app.state.session_factory, tenant_id) as session:
            project_id = await seed_project(session, tenant_id)
            seeded = await seed_artifact(
                session, tenant_id, project_id, status=status, with_missing=with_missing
            )
        return project_id, seeded

    return _seed


async def _pending(client: AsyncClient, project_id: UUID, **params: Any) -> list[dict[str, Any]]:
    response = await client.get(f"/api/v1/projects/{project_id}/pending", params=params)
    assert response.status_code == 200
    items: list[dict[str, Any]] = response.json()["items"]
    return items


def _of_kind(items: list[dict[str, Any]], kind: str) -> dict[str, Any]:
    return next(item for item in items if item["kind"] == kind)


# --- leitura -----------------------------------------------------------------------


async def test_get_project_returns_activities_and_open_pending(
    client: AsyncClient, seed: Seed
) -> None:
    # Arrange
    project_id, _ = await seed("needs_human", with_missing=True)

    # Act
    response = await client.get(f"/api/v1/projects/{project_id}")

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(project_id)
    assert len(body["activities"]) == 1
    assert body["open_pending"] == 3  # divergência do Checker + 2 lacunas do rascunho


async def test_unknown_project_returns_404(client: AsyncClient) -> None:
    for path in ("", "/pending", "/dossier"):
        response = await client.get(f"/api/v1/projects/{uuid4()}{path}")
        assert response.status_code == 404


async def test_needs_human_opens_checker_and_missing_pending(
    client: AsyncClient, seed: Seed
) -> None:
    # Arrange
    project_id, seeded = await seed("needs_human", with_missing=True)

    # Act
    items = await _pending(client, project_id)

    # Assert
    kinds = sorted(item["kind"] for item in items)
    assert kinds == ["checker_disagreement", "missing_justification", "missing_justification"]
    assert all(item["artifact_id"] == str(seeded.artifact.id) for item in items)
    assert all(item["artifact_status"] == "needs_human" for item in items)
    assert all(item["status"] == "open" for item in items)


async def test_verified_opens_approval_pending_and_projection_is_idempotent(
    client: AsyncClient, seed: Seed
) -> None:
    # Arrange
    project_id, _ = await seed("verified")

    # Act
    first = await _pending(client, project_id)
    second = await _pending(client, project_id)

    # Assert
    assert [item["kind"] for item in first] == ["approval_required"]
    assert first[0]["assignee_role"] == "manager"
    assert [item["id"] for item in second] == [item["id"] for item in first]


async def test_artifact_without_verdict_opens_no_pending(client: AsyncClient, seed: Seed) -> None:
    project_id, _ = await seed(None)

    assert await _pending(client, project_id) == []


async def test_pending_is_paginated(client: AsyncClient, seed: Seed) -> None:
    # Arrange
    project_id, _ = await seed("needs_human", with_missing=True)

    # Act
    response = await client.get(
        f"/api/v1/projects/{project_id}/pending", params={"limit": 2, "offset": 0}
    )
    rest = await client.get(
        f"/api/v1/projects/{project_id}/pending", params={"limit": 2, "offset": 2}
    )

    # Assert
    assert len(response.json()["items"]) == 2
    assert response.json()["next_offset"] == 2
    assert len(rest.json()["items"]) == 1
    assert rest.json()["next_offset"] is None


# --- resposta humana --------------------------------------------------------------


async def test_answer_records_user_correction_superseding_the_artifact(
    app: FastAPI, client: AsyncClient, seed: Seed, tenant_id: UUID
) -> None:
    # Arrange
    project_id, seeded = await seed("needs_human", with_missing=True)
    missing = _of_kind(await _pending(client, project_id), "missing_justification")

    # Act
    response = await client.post(
        f"/api/v1/pending/{missing['id']}/answer",
        json={"answer": "Hipótese: SMOTE reduz o viés de classe; sucesso = recall ≥ baseline."},
        headers=RESEARCHER,
    )

    # Assert
    assert response.status_code == 201
    body = response.json()
    assert body["pending"]["status"] == "answered"
    assert body["pending"]["artifact_status"] == "draft"
    async with tenant_session(app.state.session_factory, tenant_id) as session:
        ledger = EvidenceService(session)
        correction = await ledger.get(tenant_id, UUID(body["correction_event_id"]))
        original = await ledger.get(tenant_id, seeded.artifact.id)
    assert correction.kind is EventKind.USER_CORRECTION
    assert correction.supersedes == seeded.artifact.id
    assert correction.actor.id == str(USER)
    assert correction.payload["identity_verified"] is False
    assert original.content_hash == seeded.artifact.content_hash  # o original não muda


async def test_answering_twice_returns_409(client: AsyncClient, seed: Seed) -> None:
    # Arrange
    project_id, _ = await seed("needs_human", with_missing=True)
    item = _of_kind(await _pending(client, project_id), "checker_disagreement")
    url = f"/api/v1/pending/{item['id']}/answer"
    await client.post(url, json={"answer": "Correção do registro."}, headers=RESEARCHER)

    # Act
    response = await client.post(url, json={"answer": "De novo."}, headers=RESEARCHER)

    # Assert
    assert response.status_code == 409
    assert response.json()["code"] == "pending_closed"


async def test_approval_pending_cannot_be_answered(client: AsyncClient, seed: Seed) -> None:
    project_id, _ = await seed("verified")
    item = _of_kind(await _pending(client, project_id), "approval_required")

    response = await client.post(
        f"/api/v1/pending/{item['id']}/answer", json={"answer": "Aprovo."}, headers=MANAGER
    )

    assert response.status_code == 409
    assert response.json()["code"] == "approval_via_artifact_endpoint"


async def test_answer_of_unknown_pending_returns_404(client: AsyncClient) -> None:
    response = await client.post(
        f"/api/v1/pending/{uuid4()}/answer", json={"answer": "x"}, headers=RESEARCHER
    )

    assert response.status_code == 404


# --- aprovação formal -------------------------------------------------------------


async def test_manager_approves_verified_artifact(
    app: FastAPI, client: AsyncClient, seed: Seed, tenant_id: UUID
) -> None:
    # Arrange
    project_id, seeded = await seed("verified")
    url = f"/api/v1/artifacts/{seeded.artifact.id}/approval"

    # Act
    response = await client.post(url, json={"decision": "approve"}, headers=MANAGER)
    again = await client.post(url, json={"decision": "approve"}, headers=MANAGER)

    # Assert
    assert response.status_code == 201
    assert response.json()["status"] == "approved"
    assert again.status_code == 409
    assert again.json()["code"] == "already_decided"
    async with tenant_session(app.state.session_factory, tenant_id) as session:
        event = await EvidenceService(session).get(
            tenant_id, UUID(response.json()["evidence_event_id"])
        )
    assert event.kind is EventKind.USER_CONFIRMATION
    assert event.payload["identity_verified"] is False
    items = await _pending(client, project_id)
    assert items[0]["status"] == "resolved"
    assert items[0]["artifact_status"] == "approved"


async def test_approval_is_blocked_by_open_pending(client: AsyncClient, seed: Seed) -> None:
    _, seeded = await seed("verified", with_missing=True)

    response = await client.post(
        f"/api/v1/artifacts/{seeded.artifact.id}/approval",
        json={"decision": "approve"},
        headers=MANAGER,
    )

    assert response.status_code == 409
    assert response.json()["code"] == "open_pending"


async def test_needs_human_cannot_be_approved_but_can_be_rejected(
    client: AsyncClient, seed: Seed
) -> None:
    # Arrange
    _, seeded = await seed("needs_human")
    url = f"/api/v1/artifacts/{seeded.artifact.id}/approval"

    # Act
    approve = await client.post(url, json={"decision": "approve"}, headers=MANAGER)
    reject = await client.post(
        url, json={"decision": "reject", "comment": "Sem evidência."}, headers=MANAGER
    )

    # Assert
    assert approve.status_code == 409
    assert approve.json() == {
        "detail": "só artefato verificado pode ser aprovado",
        "code": "artifact_not_verified",
        "current_status": "needs_human",
    }
    assert reject.status_code == 201
    assert reject.json()["status"] == "rejected"


async def test_corrected_artifact_cannot_be_approved(client: AsyncClient, seed: Seed) -> None:
    # Arrange: resposta humana devolve o artefato para draft (o Maker refaz)
    project_id, seeded = await seed("verified", with_missing=True)
    missing = _of_kind(await _pending(client, project_id), "missing_justification")
    await client.post(
        f"/api/v1/pending/{missing['id']}/answer", json={"answer": "Resposta."}, headers=RESEARCHER
    )

    # Act
    response = await client.post(
        f"/api/v1/artifacts/{seeded.artifact.id}/approval",
        json={"decision": "approve"},
        headers=MANAGER,
    )

    # Assert
    assert response.status_code == 409
    assert response.json()["current_status"] == "draft"


async def test_researcher_cannot_decide_formally(client: AsyncClient, seed: Seed) -> None:
    _, seeded = await seed("verified")

    response = await client.post(
        f"/api/v1/artifacts/{seeded.artifact.id}/approval",
        json={"decision": "approve"},
        headers=RESEARCHER,
    )

    assert response.status_code == 403


async def test_human_actions_require_the_bff_secret(client: AsyncClient, seed: Seed) -> None:
    # Arrange
    _, seeded = await seed("verified")
    url = f"/api/v1/artifacts/{seeded.artifact.id}/approval"

    # Act
    forged = await client.post(
        url,
        json={"decision": "approve"},
        headers={**MANAGER, "X-Basho-Identity-Secret": "wrong"},
    )
    anonymous = await client.post(url, json={"decision": "approve"})

    # Assert
    assert forged.status_code == 401
    assert anonymous.status_code == 401


async def test_human_actions_are_closed_without_configured_secret(api_url: URL) -> None:
    app = create_app_for(api_url, uuid4(), secret=None)

    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http,
    ):
        response = await http.post(
            f"/api/v1/artifacts/{uuid4()}/approval", json={"decision": "approve"}, headers=MANAGER
        )

    assert response.status_code == 503


async def test_unknown_artifact_returns_404(client: AsyncClient) -> None:
    response = await client.post(
        f"/api/v1/artifacts/{uuid4()}/approval", json={"decision": "approve"}, headers=MANAGER
    )

    assert response.status_code == 404


# --- dossiê -----------------------------------------------------------------------


async def test_dossier_has_sources_verdicts_history_and_decision(
    client: AsyncClient, seed: Seed
) -> None:
    # Arrange
    project_id, seeded = await seed("verified")
    await client.post(
        f"/api/v1/artifacts/{seeded.artifact.id}/approval",
        json={"decision": "approve"},
        headers=MANAGER,
    )

    # Act
    response = await client.get(f"/api/v1/projects/{project_id}/dossier")

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["project"]["id"] == str(project_id)
    [entry] = body["entries"]
    assert entry["status"] == "approved"
    assert {source["id"] for source in entry["evidence"]} == {str(i) for i in seeded.cited}
    assert len(entry["verifications"]) == 2  # determinístico + Checker
    assert [event["kind"] for event in entry["history"]] == [
        "activity_record",
        "verification_result",
        "user_confirmation",
    ]
    assert entry["approval"]["decision"] == "approve"
    assert entry["runs"] == []


# --- tenant, privilégios, append-only ---------------------------------------------


async def test_project_of_another_tenant_is_invisible(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    # Arrange: projeto e artefato no tenant B; a app atende o tenant A
    other = uuid4()
    async with tenant_session(session_factory, other) as session:
        project_id = await seed_project(session, other)
        seeded = await seed_artifact(session, other, project_id, status="verified")

    # Act
    project = await client.get(f"/api/v1/projects/{project_id}")
    approval = await client.post(
        f"/api/v1/artifacts/{seeded.artifact.id}/approval",
        json={"decision": "approve"},
        headers=MANAGER,
    )

    # Assert
    assert project.status_code == 404
    assert approval.status_code == 404


@pytest.mark.parametrize("table", ["pending_answers", "artifact_approvals"])
async def test_worker_cannot_record_human_decisions(
    worker_session_factory: async_sessionmaker[AsyncSession], table: str
) -> None:
    with pytest.raises(DBAPIError, match="permission denied"):
        async with tenant_session(worker_session_factory, uuid4()) as session:
            await session.execute(text(f"INSERT INTO {table} DEFAULT VALUES"))


@pytest.mark.parametrize("table", ["projects", "pending_items", "artifact_approvals"])
async def test_app_cannot_update_projection_tables(
    session_factory: async_sessionmaker[AsyncSession], table: str
) -> None:
    with pytest.raises(DBAPIError, match="permission denied"):
        async with tenant_session(session_factory, uuid4()) as session:
            await session.execute(text(f"UPDATE {table} SET tenant_id = tenant_id"))  # noqa: S608
