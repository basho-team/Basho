"""Fila + worker + API de runs com Postgres real (#10, #23, #25). LLM sempre mockado."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import anthropic
import httpx2
import psycopg
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from psycopg import sql
from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from basho.agent.artifacts import ResearchReportDraft
from basho.agent.llm import ModelSettings
from basho.agent.maker import PERSIST_FAILED, MakerResult, MakerStatus
from basho.agent.run_service import (
    MAX_ACTIVE_RUNS_PER_REQUESTER,
    AgentRunService,
    ResearchReportRequest,
)
from basho.agent.run_store import RunStore
from basho.agent.runs import RunError, RunStatus
from basho.agent.sessions import PersistenceTransaction
from basho.agent.worker import Worker, WorkerConfig
from basho.config import Settings
from basho.db import (
    API_ROLE,
    WORKER_ROLE,
    DatabaseRoleSeparationError,
    assert_process_role,
    create_engine,
    tenant_session,
)
from basho.evidence import EvidenceService
from basho.evidence.contracts import EventKind
from basho.main import create_app
from conftest import VALID_ENV
from db_support import drop_login_role, provision_login_role, psycopg_dsn
from evidence_factories import make_event
from maker_support import FakeClient, FixedVerifier, final, tool_call
from report_factories import RESEARCHER, report

pytestmark = pytest.mark.db

Factory = async_sessionmaker[AsyncSession]
IDENTITY_SECRET = "test-identity-secret-synthetic-0123456789"  # noqa: S105 -- sintético
PERIOD = {
    "start": "2026-10-01",
    "end": "2026-10-31",
    "timezone": "America/Sao_Paulo",
    "periodicity": "monthly",
}


class Clock:
    def __init__(self) -> None:
        self.now = datetime.now(UTC) + timedelta(seconds=1)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


def _timeout() -> anthropic.APITimeoutError:
    return anthropic.APITimeoutError(request=httpx2.Request("POST", "https://api.test/v1"))


async def _seed(api: Factory, tenant_id: UUID, project_id: UUID) -> ResearchReportDraft:
    """Um commit no ledger e o rascunho válido que o Maker (mockado) vai devolver."""
    async with tenant_session(api, tenant_id) as session:
        observed = await EvidenceService(session).append(
            make_event(tenant_id=tenant_id, project_id=project_id)
        )
    return report(method_ids=(observed.id,), result_ids=(observed.id,)).model_copy(
        update={"project_id": project_id}
    )


async def _enqueue(
    api: Factory, tenant_id: UUID, draft: ResearchReportDraft, key: str | None = None
) -> UUID:
    request = ResearchReportRequest(
        project_id=draft.project_id,
        researcher_id=draft.researcher_id,
        period=draft.period,
        requested_by=uuid4(),
        idempotency_key=key,
        may_act_for_others=True,  # como o gerente
        is_synthetic=True,
    )
    async with tenant_session(api, tenant_id) as session:
        stored, _ = await AgentRunService(session).request_research_report(tenant_id, request)
    return stored.run.id


def _worker(
    factory: Factory, tenant_id: UUID, script: list[Any], clock: Clock
) -> tuple[Worker, FakeClient]:
    client = FakeClient(script)
    worker = Worker(
        factory=factory,
        client=client,
        verifier=FixedVerifier(),
        config=WorkerConfig(tenant_id=tenant_id, model=ModelSettings()),
        clock=clock,
    )
    return worker, client


async def _run(api: Factory, tenant_id: UUID, run_id: UUID) -> Any:
    async with tenant_session(api, tenant_id) as session:
        return await AgentRunService(session).get(tenant_id, run_id)


# --- fila ----------------------------------------------------------------------------


async def test_two_workers_never_claim_the_same_run(
    session_factory: Factory, worker_session_factory: Factory
) -> None:
    # Arrange
    tenant_id, project_id = uuid4(), uuid4()
    draft = await _seed(session_factory, tenant_id, project_id)
    first_id = await _enqueue(session_factory, tenant_id, draft)
    other_period = draft.period.model_copy(update={"end": draft.period.end - timedelta(days=1)})
    second_id = await _enqueue(
        session_factory, tenant_id, draft.model_copy(update={"period": other_period})
    )
    later = datetime.now(UTC) + timedelta(seconds=1)

    # Act: o primeiro worker segura o lock enquanto o segundo tenta reservar
    async with tenant_session(worker_session_factory, tenant_id) as one:
        claimed_one = await RunStore(one).claim_next(tenant_id, at=later)
        async with tenant_session(worker_session_factory, tenant_id) as two:
            claimed_two = await RunStore(two).claim_next(tenant_id, at=later)
            claimed_three = await RunStore(two).claim_next(tenant_id, at=later)

    # Assert
    assert claimed_one is not None
    assert claimed_two is not None
    assert {claimed_one.run.id, claimed_two.run.id} == {first_id, second_id}
    assert claimed_three is None
    assert claimed_one.run.status is RunStatus.RUNNING
    assert claimed_one.run.attempts == 1


async def test_worker_only_sees_runs_of_its_tenant(
    session_factory: Factory, worker_session_factory: Factory
) -> None:
    # Arrange
    owner, intruder = uuid4(), uuid4()
    draft = await _seed(session_factory, owner, uuid4())
    await _enqueue(session_factory, owner, draft)
    worker, client = _worker(worker_session_factory, intruder, [], Clock())

    # Act
    processed = await worker.process_one()

    # Assert
    assert processed is None
    assert client.messages.requests == []


# --- ponta a ponta -------------------------------------------------------------------


async def test_worker_runs_the_maker_and_completes_atomically(
    session_factory: Factory, worker_session_factory: Factory
) -> None:
    # Arrange
    tenant_id, project_id = uuid4(), uuid4()
    draft = await _seed(session_factory, tenant_id, project_id)
    run_id = await _enqueue(session_factory, tenant_id, draft)
    script = [
        tool_call("ledger_query_events", {"project_id": str(project_id)}),
        final(draft.model_dump_json()),
    ]
    worker, _ = _worker(worker_session_factory, tenant_id, script, Clock())

    # Act
    processed = await worker.process_one()

    # Assert
    assert processed == run_id
    details = await _run(session_factory, tenant_id, run_id)
    assert details.stored.run.status is RunStatus.COMPLETED
    assert details.stored.artifact_status == "verified"
    assert [call.seq for call in details.calls] == [0, 1]
    assert all(call.estimated_cost_usd is not None for call in details.calls)
    assert details.total_cost_usd is not None
    async with tenant_session(session_factory, tenant_id) as session:
        stored = await EvidenceService(session).query(tenant_id, project_id=project_id)
        audited = (
            await session.execute(
                text("SELECT count(*) FROM audit_log WHERE run_id = :run"), {"run": run_id}
            )
        ).scalar_one()
    kinds = {event.kind for event in stored}
    assert {EventKind.ACTIVITY_RECORD, EventKind.VERIFICATION_RESULT} <= kinds
    assert details.stored.artifact_event_id in {event.id for event in stored}
    assert audited == 1


async def test_transient_error_retries_with_backoff_then_fails_after_max_attempts(
    session_factory: Factory, worker_session_factory: Factory
) -> None:
    # Arrange: o tool call é auditado antes do timeout (sem transação aberta no LLM)
    tenant_id, project_id = uuid4(), uuid4()
    draft = await _seed(session_factory, tenant_id, project_id)
    run_id = await _enqueue(session_factory, tenant_id, draft)
    clock = Clock()
    script = [
        tool_call("ledger_query_events", {"project_id": str(project_id)}),
        _timeout(),
        _timeout(),
        _timeout(),
    ]
    worker, _ = _worker(worker_session_factory, tenant_id, script, clock)

    # Act / Assert: 1ª tentativa volta à fila com backoff
    assert await worker.process_one() == run_id
    first = await _run(session_factory, tenant_id, run_id)
    assert first.stored.run.status is RunStatus.QUEUED
    assert first.stored.run.error is not None
    assert first.stored.run.error.code == "provider_timeout"
    assert first.stored.run_after == clock.now + timedelta(seconds=5)
    assert len(first.calls) == 1
    assert await worker.process_one() is None  # ainda no backoff

    clock.advance(6)
    assert await worker.process_one() == run_id
    clock.advance(11)
    assert await worker.process_one() == run_id

    final_state = await _run(session_factory, tenant_id, run_id)
    assert final_state.stored.run.status is RunStatus.FAILED
    assert final_state.stored.run.attempts == final_state.stored.run.max_attempts
    async with tenant_session(session_factory, tenant_id) as session:
        audited = (
            await session.execute(
                text("SELECT count(*) FROM audit_log WHERE run_id = :run"), {"run": run_id}
            )
        ).scalar_one()
    assert audited == 1


async def test_persist_failure_rolls_back_maker_events(
    session_factory: Factory,
    worker_session_factory: Factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange: o Maker grava o rascunho e depois a gravação falha (maker_persist_failed)
    tenant_id, project_id = uuid4(), uuid4()
    draft = await _seed(session_factory, tenant_id, project_id)
    run_id = await _enqueue(session_factory, tenant_id, draft)
    worker, _ = _worker(worker_session_factory, tenant_id, [], Clock())

    class HalfPersistingMaker:
        def __init__(self, persistence: PersistenceTransaction) -> None:
            self._persistence = persistence

        async def run(self, task: Any) -> MakerResult:
            await self._persistence.append(
                make_event(
                    tenant_id=tenant_id, project_id=project_id, kind=EventKind.ACTIVITY_RECORD
                )
            )
            error = RunError(code=PERSIST_FAILED, message="o ledger rejeitou", retryable=False)
            return MakerResult(MakerStatus.FAILED, (), 1, error=error)

    monkeypatch.setattr(
        worker, "_maker", lambda stored, persistence: HalfPersistingMaker(persistence)
    )

    # Act
    await worker.process_one()

    # Assert
    details = await _run(session_factory, tenant_id, run_id)
    assert details.stored.run.status is RunStatus.FAILED
    assert details.stored.run.error is not None
    assert details.stored.run.error.code == PERSIST_FAILED
    async with tenant_session(session_factory, tenant_id) as session:
        stored = await EvidenceService(session).query(tenant_id, project_id=project_id)
    assert EventKind.ACTIVITY_RECORD not in {event.kind for event in stored}


# --- privilégios ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("role", "statement"),
    [
        ("api", "UPDATE agent_runs SET status = 'completed'"),
        ("worker", "UPDATE agent_runs SET task_input = '{}'::jsonb"),
        ("worker", "INSERT INTO agent_runs (id) VALUES (gen_random_uuid())"),
        ("worker", "UPDATE agent_calls SET latency_ms = 0"),
        ("api", "INSERT INTO agent_calls (id) VALUES (gen_random_uuid())"),
        ("api", "DELETE FROM agent_runs"),
    ],
    ids=[
        "api_cannot_update_runs",
        "worker_cannot_rewrite_task",
        "worker_cannot_create_runs",
        "calls_immutable",
        "api_cannot_write_calls",
        "no_delete",
    ],
)
async def test_app_roles_only_get_the_privileges_they_need(
    session_factory: Factory, worker_session_factory: Factory, role: str, statement: str
) -> None:
    # Arrange
    factory = session_factory if role == "api" else worker_session_factory

    # Act / Assert
    with pytest.raises(ProgrammingError, match="permission denied"):
        async with tenant_session(factory, uuid4()) as session:
            await session.execute(text(statement))


# --- API -----------------------------------------------------------------------------


def _settings(url: URL, tenant_id: UUID) -> Settings:
    env: dict[str, str | None] = {name.lower(): value for name, value in VALID_ENV.items()}
    env |= {
        "database_url": url.render_as_string(hide_password=False),
        "tenant_id": str(tenant_id),
        "reviewer_identity_secret": IDENTITY_SECRET,
    }
    return Settings.model_validate(env)


@pytest.fixture
def api_tenant() -> UUID:
    return uuid4()


@pytest.fixture
async def http(api_url: URL, api_tenant: UUID) -> AsyncIterator[AsyncClient]:
    app: FastAPI = create_app(_settings(api_url, api_tenant))
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        yield client


def _headers(
    user_id: UUID = RESEARCHER, role: str = "researcher", idempotency_key: str | None = None
) -> dict[str, str]:
    headers = {
        "X-Basho-User-Id": str(user_id),
        "X-Basho-Role": role,
        "X-Basho-Identity-Secret": IDENTITY_SECRET,
    }
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    return headers


def _body(draft: ResearchReportDraft) -> dict[str, Any]:
    return {
        "researcher_id": str(draft.researcher_id),
        "period": draft.period.model_dump(mode="json"),
    }


async def test_api_triggers_a_run_processed_end_to_end(
    http: AsyncClient,
    api_tenant: UUID,
    session_factory: Factory,
    worker_session_factory: Factory,
) -> None:
    # Arrange
    project_id = uuid4()
    draft = await _seed(session_factory, api_tenant, project_id)
    worker, _ = _worker(
        worker_session_factory, api_tenant, [final(draft.model_dump_json())], Clock()
    )

    # Act
    created = await http.post(
        f"/api/v1/projects/{project_id}/agent-runs", json=_body(draft), headers=_headers()
    )
    await worker.process_one()
    fetched = await http.get(f"/api/v1/agent-runs/{created.json()['id']}")

    # Assert
    assert created.status_code == 202
    assert created.json()["status"] == "queued"
    assert fetched.status_code == 200
    body = fetched.json()
    assert (body["status"], body["artifact_status"]) == ("completed", "verified")
    assert len(body["calls"]) == 1
    assert body["calls"][0]["model"] == "claude-opus-5-5"
    assert float(body["total_estimated_cost_usd"]) > 0


async def test_api_is_idempotent_by_header(
    http: AsyncClient, api_tenant: UUID, session_factory: Factory
) -> None:
    # Arrange
    project_id = uuid4()
    draft = await _seed(session_factory, api_tenant, project_id)
    headers = _headers(idempotency_key="demo:relatorio-outubro")
    url = f"/api/v1/projects/{project_id}/agent-runs"

    # Act
    first = await http.post(url, json=_body(draft), headers=headers)
    second = await http.post(url, json=_body(draft), headers=headers)

    # Assert
    assert (first.status_code, second.status_code) == (202, 200)
    assert first.json()["id"] == second.json()["id"]


@pytest.mark.parametrize(
    ("headers", "body", "expected"),
    [
        ({}, {"researcher_id": str(uuid4()), "period": PERIOD}, 401),
        (None, {"researcher_id": str(uuid4())}, 422),
        (None, {"researcher_id": "x", "period": {}}, 422),
    ],
    ids=["without_identity", "without_period", "invalid_body"],
)
async def test_api_rejects_untrusted_or_invalid_requests(
    http: AsyncClient, headers: dict[str, str] | None, body: dict[str, Any], expected: int
) -> None:
    # Act
    response = await http.post(
        f"/api/v1/projects/{uuid4()}/agent-runs",
        json=body,
        headers=_headers() if headers is None else headers,
    )

    # Assert
    assert response.status_code == expected


async def test_unknown_run_is_404(http: AsyncClient) -> None:
    response = await http.get(f"/api/v1/agent-runs/{uuid4()}")
    assert response.status_code == 404


async def test_same_active_task_returns_the_same_run_without_a_key(
    http: AsyncClient, api_tenant: UUID, session_factory: Factory
) -> None:
    # Arrange
    project_id = uuid4()
    draft = await _seed(session_factory, api_tenant, project_id)
    url = f"/api/v1/projects/{project_id}/agent-runs"

    # Act
    first = await http.post(url, json=_body(draft), headers=_headers())
    second = await http.post(url, json=_body(draft), headers=_headers())

    # Assert: um run ativo por tarefa (teto de custo)
    assert (first.status_code, second.status_code) == (202, 200)
    assert first.json()["id"] == second.json()["id"]


async def test_requester_is_capped_on_active_runs(
    http: AsyncClient, api_tenant: UUID, session_factory: Factory
) -> None:
    # Arrange: tarefas diferentes (períodos diferentes) do mesmo pesquisador
    project_id = uuid4()
    draft = await _seed(session_factory, api_tenant, project_id)
    url = f"/api/v1/projects/{project_id}/agent-runs"

    def body(day: int) -> dict[str, Any]:
        period = draft.period.model_copy(update={"end": draft.period.start + timedelta(days=day)})
        return {"researcher_id": str(RESEARCHER), "period": period.model_dump(mode="json")}

    # Act
    statuses = [
        (await http.post(url, json=body(day), headers=_headers())).status_code
        for day in range(MAX_ACTIVE_RUNS_PER_REQUESTER + 1)
    ]

    # Assert
    assert statuses == [202] * MAX_ACTIVE_RUNS_PER_REQUESTER + [429]


async def test_idempotency_key_reused_for_another_task_conflicts(
    http: AsyncClient, api_tenant: UUID, session_factory: Factory
) -> None:
    # Arrange
    project_id = uuid4()
    draft = await _seed(session_factory, api_tenant, project_id)
    url = f"/api/v1/projects/{project_id}/agent-runs"
    headers = _headers(idempotency_key="demo:chave-reusada")
    other = draft.period.model_copy(update={"end": draft.period.start})

    # Act
    await http.post(url, json=_body(draft), headers=headers)
    reused = await http.post(
        url,
        json={"researcher_id": str(RESEARCHER), "period": other.model_dump(mode="json")},
        headers=headers,
    )

    # Assert
    assert reused.status_code == 409


@pytest.mark.parametrize(
    ("user_id", "role", "expected"),
    [(uuid4(), "researcher", 403), (uuid4(), "manager", 202), (RESEARCHER, "researcher", 202)],
    ids=["researcher_for_another", "manager_for_anyone", "researcher_for_self"],
)
async def test_only_managers_request_reports_for_other_researchers(
    http: AsyncClient,
    api_tenant: UUID,
    session_factory: Factory,
    user_id: UUID,
    role: str,
    expected: int,
) -> None:
    # Arrange
    project_id = uuid4()
    draft = await _seed(session_factory, api_tenant, project_id)

    # Act
    response = await http.post(
        f"/api/v1/projects/{project_id}/agent-runs",
        json=_body(draft),
        headers=_headers(user_id=user_id, role=role),
    )

    # Assert
    assert response.status_code == expected


async def test_process_role_rejects_a_login_in_both_groups(
    migrated_ledger_url: URL, api_url: URL
) -> None:
    # Arrange: login de teste membro de basho_api **e** de basho_worker
    login = f"basho_test_dual_{uuid4().hex[:8]}"
    url = provision_login_role(migrated_ledger_url, login, "basho_api")
    with psycopg.connect(
        psycopg_dsn(migrated_ledger_url, migrated_ledger_url.database or "")
    ) as admin:
        admin.execute(sql.SQL("GRANT basho_worker TO {}").format(sql.Identifier(login)))
    engine = create_engine(url.render_as_string(hide_password=False))
    api_only = create_engine(api_url.render_as_string(hide_password=False))

    # Act / Assert
    try:
        with pytest.raises(DatabaseRoleSeparationError):
            await assert_process_role(engine, required=WORKER_ROLE, forbidden=API_ROLE)
        with pytest.raises(DatabaseRoleSeparationError):
            await assert_process_role(engine, required=API_ROLE, forbidden=WORKER_ROLE)
        await assert_process_role(api_only, required=API_ROLE, forbidden=WORKER_ROLE)
        with pytest.raises(DatabaseRoleSeparationError):
            await assert_process_role(api_only, required=WORKER_ROLE, forbidden=API_ROLE)
    finally:
        await engine.dispose()
        await api_only.dispose()
        drop_login_role(migrated_ledger_url, login)
