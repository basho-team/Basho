"""Endpoints `/api/v1/reports` com Postgres real (GET, POST review, 409, 401, 403, 422)."""

from collections.abc import AsyncIterator, Awaitable, Callable
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine import URL

from basho.config import Settings
from basho.db import tenant_session
from basho.main import create_app
from basho.reports.schemas import ReportVersionOut
from conftest import VALID_ENV
from report_factories import RESEARCHER, seed_report

pytestmark = pytest.mark.db

PENDING_CLAIM = 3
HYPOTHESIS = "Hipótese registrada: SMOTE reduz o viés de classe sem perda de recall."
RESEARCHER_HEADERS = {"X-Basho-User-Id": str(RESEARCHER), "X-Basho-Role": "researcher"}


def _settings(url: URL, tenant_id: UUID) -> Settings:
    env = {name.lower(): value for name, value in VALID_ENV.items()}
    env["database_url"] = url.render_as_string(hide_password=False)
    env["tenant_id"] = str(tenant_id)
    return Settings.model_validate(env)


@pytest.fixture
def tenant_id() -> UUID:
    return uuid4()


@pytest.fixture
async def app(migrated_ledger_url: URL, tenant_id: UUID) -> AsyncIterator[FastAPI]:
    created = create_app(_settings(migrated_ledger_url, tenant_id))
    yield created
    await created.state.engine.dispose()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


Seed = Callable[[], Awaitable[ReportVersionOut]]


@pytest.fixture
def seed(app: FastAPI, tenant_id: UUID) -> Seed:
    """Grava a v1 de um relatório sintético no tenant da app."""

    async def _seed() -> ReportVersionOut:
        async with tenant_session(app.state.session_factory, tenant_id) as session:
            _, created = await seed_report(session, tenant_id, uuid4())
        return created

    return _seed


def _correction_body(v1: ReportVersionOut) -> dict[str, object]:
    return {
        "decision": "changes_requested",
        "comment": "Hipótese estava sem registro.",
        "correction": {
            "reason": "Pesquisador registrou a hipótese.",
            "operations": [
                {
                    "kind": "revise_claim",
                    "claim_id": str(v1.version.claim_ids[PENDING_CLAIM]),
                    "text": HYPOTHESIS,
                    "status": "supported",
                    "evidence_ids": [str(v1.version.draft.claims[0].evidence_ids[0])],
                }
            ],
        },
    }


async def test_get_report_returns_version_and_status(client: AsyncClient, seed: Seed) -> None:
    # Arrange
    v1 = await seed()

    # Act
    response = await client.get(f"/api/v1/reports/{v1.version.id}")

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["version"]["id"] == str(v1.version.id)
    assert body["is_current"] is True
    assert body["status"]["researcher"]["state"] == "awaiting_review"


async def test_get_unknown_report_returns_404(client: AsyncClient) -> None:
    response = await client.get(f"/api/v1/reports/{uuid4()}")

    assert response.status_code == 404


async def test_review_current_version_returns_201(client: AsyncClient, seed: Seed) -> None:
    # Arrange
    v1 = await seed()

    # Act
    response = await client.post(
        f"/api/v1/reports/{v1.version.id}/review",
        json={"decision": "text_approved"},
        headers=RESEARCHER_HEADERS,
    )

    # Assert
    assert response.status_code == 201
    assert response.json()["review"]["version_id"] == str(v1.version.id)
    status = (await client.get(f"/api/v1/reports/{v1.version.id}")).json()["status"]
    assert status["researcher"]["state"] == "text_approved"


async def test_review_of_old_version_returns_409_with_current_id(
    client: AsyncClient, seed: Seed
) -> None:
    # Arrange
    v1 = await seed()
    corrected = await client.post(
        f"/api/v1/reports/{v1.version.id}/review",
        json=_correction_body(v1),
        headers=RESEARCHER_HEADERS,
    )
    v2_id = corrected.json()["new_version"]["id"]

    # Act
    response = await client.post(
        f"/api/v1/reports/{v1.version.id}/review",
        json={"decision": "text_approved"},
        headers=RESEARCHER_HEADERS,
    )

    # Assert
    assert corrected.status_code == 201
    assert response.status_code == 409
    assert response.json()["requested_version_id"] == str(v1.version.id)
    assert response.json()["current_version_id"] == v2_id
    v2_status = (await client.get(f"/api/v1/reports/{v2_id}")).json()["status"]
    assert v2_status["researcher"]["state"] == "awaiting_review"


async def test_review_without_identity_returns_401(client: AsyncClient, seed: Seed) -> None:
    v1 = await seed()

    response = await client.post(
        f"/api/v1/reports/{v1.version.id}/review", json={"decision": "text_approved"}
    )

    assert response.status_code == 401


async def test_review_as_researcher_by_non_author_returns_403(
    client: AsyncClient, seed: Seed
) -> None:
    v1 = await seed()

    response = await client.post(
        f"/api/v1/reports/{v1.version.id}/review",
        json={"decision": "text_approved"},
        headers={"X-Basho-User-Id": str(uuid4()), "X-Basho-Role": "researcher"},
    )

    assert response.status_code == 403


async def test_correction_with_unknown_item_returns_422(client: AsyncClient, seed: Seed) -> None:
    # Arrange
    v1 = await seed()
    body = _correction_body(v1)
    body["correction"]["operations"][0]["claim_id"] = str(uuid4())  # type: ignore[index]

    # Act
    response = await client.post(
        f"/api/v1/reports/{v1.version.id}/review", json=body, headers=RESEARCHER_HEADERS
    )

    # Assert
    assert response.status_code == 422
    assert (await client.get(f"/api/v1/reports/{v1.version.id}")).json()["is_current"] is True


async def test_correction_with_approval_is_rejected_at_the_edge(
    client: AsyncClient, seed: Seed
) -> None:
    v1 = await seed()
    body = {**_correction_body(v1), "decision": "text_approved"}

    response = await client.post(
        f"/api/v1/reports/{v1.version.id}/review", json=body, headers=RESEARCHER_HEADERS
    )

    assert response.status_code == 422
