"""Jornada pela API com Postgres real: evidência → relatório → checks → correção (409 na
versão antiga) → confirmação da versão exata → consolidação → dossiê; isolamento de tenant."""

from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine import URL

from basho.config import Settings
from basho.main import create_app
from conftest import VALID_ENV

pytestmark = pytest.mark.db

IDENTITY_SECRET = "test-identity-secret-synthetic-journey-0123"  # noqa: S105 -- sintético


def _settings(url: URL, tenant_id: UUID) -> Settings:
    env: dict[str, str | None] = {name.lower(): value for name, value in VALID_ENV.items()}
    env["database_url"] = url.render_as_string(hide_password=False)
    env["tenant_id"] = str(tenant_id)
    env["reviewer_identity_secret"] = IDENTITY_SECRET
    return Settings.model_validate(env)


ANA = UUID("33333333-3333-4333-8333-333333333333")
CARLA = UUID("55555555-5555-4555-8555-555555555555")
Q = {"start": "2026-10-01", "end": "2026-10-31"}


def _who(user: UUID, role: str) -> dict[str, str]:
    return {
        "X-Basho-User-Id": str(user),
        "X-Basho-Role": role,
        "X-Basho-Identity-Secret": IDENTITY_SECRET,
    }


ANA_H = _who(ANA, "researcher")


@pytest.fixture
async def app(api_url: URL) -> AsyncIterator[FastAPI]:
    created = create_app(_settings(api_url, uuid4()))
    async with created.router.lifespan_context(created):
        yield created


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


async def _evidence(client: AsyncClient, project: UUID, **body: Any) -> str:
    response = await client.post(f"/api/v1/projects/{project}/evidence", json=body, headers=ANA_H)
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _draft(project: UUID, activity: str, result: str, text: str) -> dict[str, Any]:
    return {
        "project_id": str(project),
        "researcher_id": str(ANA),
        "period": {**Q, "timezone": "America/Sao_Paulo", "periodicity": "monthly"},
        "summary": "Quantização int8 e rebalanceamento do dataset no período.",
        "claims": [
            {"section": "method", "text": text, "status": "supported", "evidence_ids": [activity]},
            {
                "section": "result",
                "text": "Precisão caiu 4,1 p.p. após quantização.",
                "status": "supported",
                "evidence_ids": [result],
            },
            {
                "section": "hypothesis",
                "text": "Hipótese do rebalanceamento ainda não registrada.",
                "status": "pending",
                "question": "Qual hipótese motivou o rebalanceamento?",
                "ask_role": "pesquisador",
            },
        ],
        "experiments": [
            {
                "description": "Quantização int8 dinâmica no modelo embarcado.",
                "outcome": "negative",
                "evidence_ids": [result],
            }
        ],
        "missing": [
            {
                "field": "formal_hours",
                "ask_role": "coordenador",
                "question": "Quais horas o registro formal informa para o período?",
            }
        ],
    }


async def test_full_journey_researcher_manager_fiscal(client: AsyncClient) -> None:
    project = uuid4()
    activity = await _evidence(
        client,
        project,
        kind="activity_record",
        title="Quantização int8",
        description="Aplicação de int8 dinâmico.",
    )
    result = await _evidence(
        client,
        project,
        kind="technical_justification",
        title="Benchmark",
        description="Precisão caiu 4,1 p.p. após int8.",
    )
    hours = await _evidence(
        client,
        project,
        kind="formal_hours_declared",
        hours=80,
        title="Horas outubro",
        description="Declaração formal do período.",
    )

    # relatório v1 com horas no texto → check determinístico acusa
    bad = _draft(project, activity, result, "Ana dedicou 40 horas à quantização int8.")
    created = await client.post("/api/v1/reports", json=bad, headers=ANA_H)
    assert created.status_code == 201, created.text
    v1 = created.json()["version"]
    checks = (await client.post(f"/api/v1/reports/{v1['id']}/checks")).json()
    assert checks["checker_status"] == "unavailable"
    assert "formal_data_in_text" in {i["code"] for i in checks["deterministic"]["issues"]}

    # correção: retira as horas do texto e fecha a lacuna com o evento formal
    method_id, gap_id = v1["claim_ids"][0], v1["missing_ids"][0]
    correction = {
        "decision": "changes_requested",
        "comment": "Horas não podem estar no texto.",
        "correction": {
            "reason": "Remover horas do texto e citar o registro formal.",
            "operations": [
                {
                    "kind": "revise_claim",
                    "claim_id": method_id,
                    "status": "supported",
                    "text": "Aplicação de quantização int8 dinâmica no modelo embarcado.",
                    "evidence_ids": [activity],
                },
                {
                    "kind": "resolve_missing",
                    "missing_id": gap_id,
                    "formal_hours_event_ids": [hours],
                },
            ],
        },
    }
    reviewed = await client.post(
        f"/api/v1/reports/{v1['id']}/review", json=correction, headers=ANA_H
    )
    assert reviewed.status_code == 201, reviewed.text
    v2 = reviewed.json()["new_version"]
    assert v2["number"] == 2 and v2["claim_ids"][0] == method_id

    # confirmar a v1 (desatualizada) → 409; confirmar a v2 exata → 201
    approve = {"decision": "text_approved"}
    stale = await client.post(f"/api/v1/reports/{v1['id']}/review", json=approve, headers=ANA_H)
    assert stale.status_code == 409
    assert stale.json()["current_version_id"] == v2["id"]
    ok = await client.post(f"/api/v1/reports/{v2['id']}/review", json=approve, headers=ANA_H)
    assert ok.status_code == 201, ok.text
    review_id = ok.json()["review"]["id"]
    clean = (await client.post(f"/api/v1/reports/{v2['id']}/checks")).json()
    assert clean["deterministic"]["verdict"] == "pass", clean

    history = (await client.get(f"/api/v1/reports/{v2['id']}/history")).json()
    assert [h["version"]["number"] for h in history] == [1, 2]

    # gerente: consolidação com a v2 aprovada e o negativo preservado
    cons = (await client.get(f"/api/v1/projects/{project}/consolidation", params=Q)).json()
    assert cons["consolidation"]["all_text_approved"] is True
    assert cons["consolidation"]["outcome_counts"]["negative"] == 1
    assert "Negativo" in cons["summary_markdown"]

    # fiscal: dossiê com origem verificável e revisão do pesquisador pelo ID exato
    dossier = (
        await client.get(f"/api/v1/projects/{project}/dossier", params={**Q, "fiscal_year": 2026})
    ).json()
    (researcher,) = dossier["researchers"]
    assert researcher["researcher_review_id"] == review_id
    assert [s["reference"] for s in researcher["formal_hours"]] == [f"evidence:{hours}"]
    negative = next(i for i in dossier["items"] if i["status"] == "result_negative")
    assert negative["sources"][0]["locator"].startswith(f"report:{v2['id']}/experiment/")


async def test_only_the_researcher_creates_own_report_and_citations_must_exist(
    client: AsyncClient,
) -> None:
    project = uuid4()
    activity = await _evidence(
        client,
        project,
        kind="activity_record",
        title="Atividade",
        description="Atividade de P&D registrada.",
    )
    draft = _draft(project, activity, activity, "Método aplicado conforme registro.")
    as_manager = await client.post("/api/v1/reports", json=draft, headers=_who(CARLA, "manager"))
    assert as_manager.status_code == 403
    fake = _draft(project, str(uuid4()), activity, "Método aplicado conforme registro.")
    assert (await client.post("/api/v1/reports", json=fake, headers=ANA_H)).status_code == 422
    unauthenticated = await client.post("/api/v1/reports", json=draft)
    assert unauthenticated.status_code == 401


async def test_hours_only_in_formal_hours_kind(client: AsyncClient) -> None:
    project = uuid4()
    url = f"/api/v1/projects/{project}/evidence"
    with_hours = {
        "kind": "activity_record",
        "title": "Atividade",
        "hours": 3,
        "description": "Horas não podem vir em atividade.",
    }
    assert (await client.post(url, json=with_hours, headers=ANA_H)).status_code == 422
    agent_kind = {
        "kind": "commit_observed",
        "title": "Commit",
        "description": "Humano não registra evento de GitHub.",
    }
    assert (await client.post(url, json=agent_kind, headers=ANA_H)).status_code == 422


async def test_other_tenant_sees_nothing(client: AsyncClient, api_url: URL) -> None:
    project = uuid4()
    await _evidence(
        client,
        project,
        kind="activity_record",
        title="Atividade",
        description="Atividade do tenant A.",
    )
    other = create_app(_settings(api_url, uuid4()))
    async with (
        other.router.lifespan_context(other),
        AsyncClient(transport=ASGITransport(app=other), base_url="http://test") as http,
    ):
        assert (await http.get(f"/api/v1/projects/{project}/evidence")).json() == []
        assert (await http.get(f"/api/v1/projects/{project}/reports", params=Q)).json() == []
        dossier = await http.get(
            f"/api/v1/projects/{project}/dossier", params={**Q, "fiscal_year": 2026}
        )
        assert dossier.status_code == 404


async def test_demo_context_reports_ai_unavailable_without_keys(client: AsyncClient) -> None:
    # VALID_ENV usa chaves de teste: a rota só diz "disponível" quando há chave de fato.
    body = (await client.get("/api/v1/demo/context")).json()
    assert body["is_synthetic"] is True
    assert isinstance(body["ai_maker_available"], bool)
    assert "não são acionados pela interface" in body["ai_detail"]
