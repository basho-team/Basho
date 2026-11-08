"""Corrigir evidência citada leva o relatório a needs_review; nova versão resolve (#11)."""

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
from basho.evidence.contracts import EventKind, EventSource
from basho.main import create_app
from conftest import VALID_ENV
from evidence_factories import make_event

pytestmark = pytest.mark.db

SECRET = "test-identity-secret-synthetic-propagation-01"  # noqa: S105 -- sintético
ANA = UUID("33333333-3333-4333-8333-333333333333")
Q = {"start": "2026-10-01", "end": "2026-10-31"}
ANA_H = {
    "X-Basho-User-Id": str(ANA),
    "X-Basho-Role": "researcher",
    "X-Basho-Identity-Secret": SECRET,
}


@pytest.fixture
def tenant_id() -> UUID:
    return uuid4()


@pytest.fixture
async def app(api_url: URL, tenant_id: UUID) -> AsyncIterator[FastAPI]:
    env: dict[str, str | None] = {k.lower(): v for k, v in VALID_ENV.items()}
    env.update(
        database_url=api_url.render_as_string(hide_password=False),
        tenant_id=str(tenant_id),
        reviewer_identity_secret=SECRET,
    )
    created = create_app(Settings.model_validate(env))
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


async def test_correcting_cited_evidence_flags_report_until_new_version(
    app: FastAPI, client: AsyncClient, tenant_id: UUID
) -> None:
    project = uuid4()
    base = f"/api/v1/projects/{project}"
    pr = await _evidence(
        app,
        tenant_id,
        project,
        kind=EventKind.PULL_REQUEST_OBSERVED,
        payload={
            "title": "PR #42",
            "description": "Latência 38% menor.",
            "researcher_id": str(ANA),
        },
    )
    v1 = (await client.post(f"{base}/reports/auto-draft", params=Q, headers=ANA_H)).json()
    assert (await client.get(f"{base}/reports/needs-review", params=Q, headers=ANA_H)).json() == []

    corrected = await client.post(
        f"{base}/evidence/{pr}/correction",
        headers=ANA_H,
        json={
            "description": "Latência 31% menor (benchmark refeito).",
            "reason": "O benchmark original usou o lote de aquecimento.",
        },
    )
    assert corrected.status_code == 201, corrected.text
    correction_id = corrected.json()["correction_event_id"]
    assert v1["evidence_event_id"] in {m["artifact_event_id"] for m in corrected.json()["marked"]}

    flags = (await client.get(f"{base}/reports/needs-review", params=Q, headers=ANA_H)).json()
    assert [f["report_version_id"] for f in flags] == [v1["version"]["id"]]
    assert flags[0]["superseded_event_id"] == str(pr)
    cons = (await client.get(f"{base}/consolidation", params=Q, headers=ANA_H)).json()
    assert [f["report_version_id"] for f in cons["needs_review"]] == [v1["version"]["id"]]

    claim_id = v1["version"]["claim_ids"][0]
    review = {
        "decision": "changes_requested",
        "comment": "Evidência corrigida.",
        "correction": {
            "reason": "Citar o benchmark refeito.",
            "operations": [
                {
                    "kind": "revise_claim",
                    "claim_id": claim_id,
                    "status": "supported",
                    "text": "PR #42: latência 31% menor (benchmark refeito).",
                    "evidence_ids": [correction_id],
                },
            ],
        },
    }
    reviewed = await client.post(
        f"/api/v1/reports/{v1['version']['id']}/review", json=review, headers=ANA_H
    )
    assert reviewed.status_code == 201, reviewed.text
    assert (await client.get(f"{base}/reports/needs-review", params=Q, headers=ANA_H)).json() == []


async def test_formal_hours_and_unknown_evidence_are_not_corrected_here(
    app: FastAPI, client: AsyncClient, tenant_id: UUID
) -> None:
    project = uuid4()
    hours = await _evidence(
        app,
        tenant_id,
        project,
        kind=EventKind.FORMAL_HOURS_DECLARED,
        source=EventSource.FORMAL_SYSTEM,
        payload={"hours": 96},
    )
    body = {"description": "Horas alteradas pela pessoa.", "reason": "Tentativa de ajuste."}
    url = f"/api/v1/projects/{project}/evidence"
    assert (
        await client.post(f"{url}/{hours}/correction", json=body, headers=ANA_H)
    ).status_code == 422
    assert (
        await client.post(f"{url}/{uuid4()}/correction", json=body, headers=ANA_H)
    ).status_code == 404
    assert (await client.post(f"{url}/{hours}/correction", json=body)).status_code == 401
