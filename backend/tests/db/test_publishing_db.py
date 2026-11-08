"""Links autorizados e publicação autônoma (ADR-0010) com Postgres real e destinos falsos."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from basho.agent.llm import ModelSettings
from basho.agent.worker import Worker, WorkerConfig
from basho.config import Settings
from basho.db import tenant_session
from basho.main import create_app
from basho.publishing import (
    IntegrationRegistry,
    LinkKind,
    PublicationWorker,
    PublishedDoc,
    PublishingService,
    parse_link,
)
from basho.publishing.clients.errors import ProviderError, ProviderErrorCode
from basho.publishing.render import RenderedDoc
from basho.seed import seed_demo
from conftest import VALID_ENV

pytestmark = pytest.mark.db

Factory = async_sessionmaker[AsyncSession]
SECRET = "test-identity-secret-synthetic-0123456789"  # noqa: S105 -- sintético
USER = UUID("44444444-4444-4444-8444-444444444444")
DRIVE_ID = "1AbCdEfGhIjKlMnOpQrStUvWxYz012345"
DRIVE_URL = f"https://drive.google.com/drive/folders/{DRIVE_ID}?usp=sharing"
NOTION_URL = "https://www.notion.so/Meu-Projeto-0123456789abcdef0123456789abcdef"
SERVICE_ACCOUNT = "basho@projeto-sintetico.iam.gserviceaccount.com"


def _headers(role: str) -> dict[str, str]:
    return {"X-Basho-User-Id": str(USER), "X-Basho-Role": role, "X-Basho-Identity-Secret": SECRET}


MANAGER, RESEARCHER = _headers("manager"), _headers("researcher")


class FakeDestination:
    """Destino em memória: registra o que recebeu e falha sob demanda."""

    def __init__(self, kind: LinkKind, *, name: str = "Pasta de teste") -> None:
        self.kind = kind
        self.name = name
        self.check_error: ProviderError | None = None
        self.failures: list[ProviderError] = []
        self.published: list[tuple[str, RenderedDoc]] = []

    async def check(self, external_id: str) -> str:
        if self.check_error is not None:
            raise self.check_error
        return self.name

    async def publish(self, external_id: str, doc: RenderedDoc) -> PublishedDoc:
        if self.failures:
            raise self.failures.pop(0)
        self.published.append((external_id, doc))
        number = len(self.published)
        return PublishedDoc(external_id=f"ext-{number}", url=f"https://fake.example/{number}")


class Env:
    def __init__(
        self, app: FastAPI, tenant_id: UUID, drive: FakeDestination, notion: FakeDestination
    ) -> None:
        self.app, self.tenant_id, self.drive, self.notion = app, tenant_id, drive, notion


def _settings(url: URL, tenant_id: UUID) -> Settings:
    env: dict[str, str | None] = {name.lower(): value for name, value in VALID_ENV.items()}
    env["database_url"] = url.render_as_string(hide_password=False)
    env["tenant_id"] = str(tenant_id)
    env["reviewer_identity_secret"] = SECRET
    return Settings.model_validate(env)


@pytest.fixture
def tenant_id() -> UUID:
    return uuid4()


@pytest.fixture
async def env(api_url: URL, tenant_id: UUID) -> AsyncIterator[Env]:
    settings = _settings(api_url, tenant_id)
    app = create_app(settings)
    drive, notion = FakeDestination(LinkKind.DRIVE_FOLDER), FakeDestination(LinkKind.NOTION_PAGE)
    registry = IntegrationRegistry(
        settings,
        httpx.AsyncClient(),
        destinations={LinkKind.DRIVE_FOLDER: drive, LinkKind.NOTION_PAGE: notion},
    )
    registry.service_account_email = SERVICE_ACCOUNT
    app.state.integrations = registry
    async with app.router.lifespan_context(app):
        yield Env(app, tenant_id, drive, notion)


@pytest.fixture
async def client(env: Env) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=env.app), base_url="http://test") as http:
        yield http


@pytest.fixture
async def project_id(env: Env, session_factory: Factory) -> UUID:
    """Projeto da demo: 1 artefato `verified` e 1 `needs_human`."""
    async with tenant_session(session_factory, env.tenant_id) as session:
        seeded = await seed_demo(session, env.tenant_id)
    return UUID(seeded["project_id"])


def _worker(env: Env, factory: Factory, clock: Any = None) -> PublicationWorker:
    registry: IntegrationRegistry = env.app.state.integrations
    kwargs: dict[str, Any] = {"clock": clock} if clock is not None else {}
    return PublicationWorker(factory=factory, registry=registry, tenant_id=env.tenant_id, **kwargs)


async def _link(client: AsyncClient, project_id: UUID, url: str) -> dict[str, Any]:
    response = await client.post(
        f"/api/v1/projects/{project_id}/links", json={"url": url}, headers=MANAGER
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def _publish_now(client: AsyncClient, project_id: UUID) -> dict[str, Any]:
    response = await client.post(f"/api/v1/projects/{project_id}/publications", headers=MANAGER)
    assert response.status_code == 202, response.text
    body: dict[str, Any] = response.json()
    return body


# --- links ---


async def test_manager_authorizes_a_drive_link_after_the_access_check(
    client: AsyncClient, env: Env, project_id: UUID
) -> None:
    # Arrange
    env.drive.name = "Projetos 2026"

    # Act
    link = await _link(client, project_id, DRIVE_URL)

    # Assert: guarda só o ID canônico e o nome verificado (nunca a URL colada)
    assert link["kind"] == "drive_folder"
    assert link["display_name"] == "Projetos 2026"
    assert link["url"] == f"https://drive.google.com/drive/folders/{DRIVE_ID}"
    assert link["status"] == "active"


async def test_authorizing_the_same_link_twice_does_not_duplicate_it(
    client: AsyncClient, project_id: UUID
) -> None:
    # Act
    first = await _link(client, project_id, DRIVE_URL)
    second = await _link(client, project_id, DRIVE_URL + "&x=1")
    listed = (await client.get(f"/api/v1/projects/{project_id}/links", headers=RESEARCHER)).json()

    # Assert
    assert first["id"] == second["id"]
    assert len(listed) == 1


async def test_researcher_cannot_authorize_or_revoke_links(
    client: AsyncClient, project_id: UUID
) -> None:
    # Arrange
    link = await _link(client, project_id, DRIVE_URL)

    # Act
    add = await client.post(
        f"/api/v1/projects/{project_id}/links", json={"url": NOTION_URL}, headers=RESEARCHER
    )
    revoke = await client.delete(
        f"/api/v1/projects/{project_id}/links/{link['id']}", headers=RESEARCHER
    )

    # Assert
    assert add.status_code == 403
    assert revoke.status_code == 403


async def test_invalid_and_unsafe_links_are_422_without_any_network_call(
    client: AsyncClient, project_id: UUID
) -> None:
    # Act
    response = await client.post(
        f"/api/v1/projects/{project_id}/links",
        json={"url": "https://169.254.169.254/latest/meta-data/"},
        headers=MANAGER,
    )

    # Assert
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_link"


async def test_unshared_folder_gets_actionable_instructions(
    client: AsyncClient, env: Env, project_id: UUID
) -> None:
    # Arrange: pasta não compartilhada com a conta do Basho
    env.drive.check_error = ProviderError(ProviderErrorCode.NOT_FOUND)

    # Act
    response = await client.post(
        f"/api/v1/projects/{project_id}/links", json={"url": DRIVE_URL}, headers=MANAGER
    )

    # Assert: diz com quem compartilhar e não grava nada
    assert response.status_code == 422
    assert response.json()["code"] == "access_denied"
    assert SERVICE_ACCOUNT in response.json()["detail"]
    listed = (await client.get(f"/api/v1/projects/{project_id}/links", headers=MANAGER)).json()
    assert listed == []


async def test_integration_without_server_credentials_is_503(
    client: AsyncClient, env: Env, project_id: UUID
) -> None:
    # Arrange
    env.drive.check_error = ProviderError(ProviderErrorCode.NOT_CONFIGURED)

    # Act
    response = await client.post(
        f"/api/v1/projects/{project_id}/links", json={"url": DRIVE_URL}, headers=MANAGER
    )

    # Assert
    assert response.status_code == 503
    assert response.json()["code"] == "not_configured"


async def test_links_of_unknown_project_and_without_identity(client: AsyncClient) -> None:
    # Act
    unknown = await client.get(f"/api/v1/projects/{uuid4()}/links", headers=MANAGER)
    anonymous = await client.get(f"/api/v1/projects/{uuid4()}/links")

    # Assert
    assert unknown.status_code == 404
    assert anonymous.status_code == 401


async def test_integrations_config_tells_the_user_who_to_share_with(client: AsyncClient) -> None:
    # Act
    response = await client.get("/api/v1/integrations/config", headers=RESEARCHER)

    # Assert
    assert response.json() == {
        "drive": True,
        "notion": True,
        "github": False,
        "google_service_account_email": SERVICE_ACCOUNT,
    }


async def test_github_repo_link_feeds_the_agent_worker(
    session_factory: Factory, env: Env, project_id: UUID
) -> None:
    # Arrange: o worker lê o repositório do link (e não só do mapa de configuração)
    parsed = parse_link("https://github.com/basho-team/Basho")
    async with tenant_session(session_factory, env.tenant_id) as session:
        await PublishingService(session).add_link(
            env.tenant_id, project_id, parsed, display_name="basho-team/Basho", created_by=USER
        )

    # Act
    async with tenant_session(session_factory, env.tenant_id) as session:
        repo = await PublishingService(session).github_repo(env.tenant_id, project_id)

    # Assert
    assert repo == "basho-team/Basho"


# --- fila e worker ---


async def test_publish_now_enqueues_only_verified_artifacts_once_per_destination(
    client: AsyncClient, project_id: UUID
) -> None:
    # Arrange
    await _link(client, project_id, DRIVE_URL)
    await _link(client, project_id, NOTION_URL)

    # Act
    first = await _publish_now(client, project_id)
    second = await _publish_now(client, project_id)

    # Assert: 1 artefato verified x 2 destinos; o needs_human nunca entra; repetir não duplica
    assert first["queued"] == 2
    assert second["queued"] == 0
    assert len(second["items"]) == 2
    assert {item["link_kind"] for item in second["items"]} == {"drive_folder", "notion_page"}
    assert {item["status"] for item in second["items"]} == {"queued"}


async def test_publish_now_without_links_enqueues_nothing(
    client: AsyncClient, project_id: UUID
) -> None:
    # Act
    result = await _publish_now(client, project_id)

    # Assert
    assert result == {"queued": 0, "items": []}


async def test_worker_publishes_the_report_to_every_destination(
    client: AsyncClient, env: Env, project_id: UUID, worker_session_factory: Factory
) -> None:
    # Arrange
    await _link(client, project_id, DRIVE_URL)
    await _link(client, project_id, NOTION_URL)
    await _publish_now(client, project_id)
    worker = _worker(env, worker_session_factory)

    # Act
    first, second, none_left = (
        await worker.process_one(),
        await worker.process_one(),
        await worker.process_one(),
    )

    # Assert
    assert first is not None
    assert second is not None
    assert none_left is None
    items = (
        await client.get(f"/api/v1/projects/{project_id}/publications", headers=MANAGER)
    ).json()["items"]
    assert {i["status"] for i in items} == {"published"}
    assert all(i["external_url"].startswith("https://fake.example/") for i in items)
    (drive_target, drive_doc), (notion_target, _) = env.drive.published[0], env.notion.published[0]
    assert drive_target == DRIVE_ID
    assert notion_target == "01234567-89ab-cdef-0123-456789abcdef"
    html = drive_doc.to_html()
    assert "Fontes" in html
    assert "commit a1f3c9e" in html  # as afirmações citam os commits do projeto
    assert "sujeito a análise" in html


async def test_transient_failure_is_retried_with_backoff_then_succeeds(
    client: AsyncClient, env: Env, project_id: UUID, worker_session_factory: Factory
) -> None:
    # Arrange
    await _link(client, project_id, DRIVE_URL)
    await _publish_now(client, project_id)
    env.drive.failures = [ProviderError(ProviderErrorCode.UNAVAILABLE, retryable=True)]
    now = {"t": datetime.now(UTC)}
    worker = _worker(env, worker_session_factory, clock=lambda: now["t"])

    # Act
    await worker.process_one()
    right_after = await worker.process_one()  # ainda dentro do backoff
    items = (
        await client.get(f"/api/v1/projects/{project_id}/publications", headers=MANAGER)
    ).json()["items"]
    now["t"] += timedelta(seconds=30)
    await worker.process_one()
    final = (
        await client.get(f"/api/v1/projects/{project_id}/publications", headers=MANAGER)
    ).json()["items"]

    # Assert
    assert right_after is None
    assert (items[0]["status"], items[0]["error_code"], items[0]["attempts"]) == (
        "queued",
        "unavailable",
        1,
    )
    assert (final[0]["status"], final[0]["attempts"]) == ("published", 2)
    assert final[0]["error_code"] is None
    assert len(env.drive.published) == 1


async def test_permanent_failure_is_not_retried(
    client: AsyncClient, env: Env, project_id: UUID, worker_session_factory: Factory
) -> None:
    # Arrange: a pasta deixou de ser compartilhada com a conta do Basho
    await _link(client, project_id, DRIVE_URL)
    await _publish_now(client, project_id)
    env.drive.failures = [ProviderError(ProviderErrorCode.ACCESS_DENIED)]
    worker = _worker(env, worker_session_factory)

    # Act
    await worker.process_one()
    again = await worker.process_one()
    items = (
        await client.get(f"/api/v1/projects/{project_id}/publications", headers=MANAGER)
    ).json()["items"]

    # Assert
    assert again is None
    assert (items[0]["status"], items[0]["error_code"]) == ("failed", "access_denied")


async def test_retryable_failure_gives_up_after_the_attempt_limit(
    client: AsyncClient, env: Env, project_id: UUID, worker_session_factory: Factory
) -> None:
    # Arrange
    await _link(client, project_id, DRIVE_URL)
    await _publish_now(client, project_id)
    env.drive.failures = [ProviderError(ProviderErrorCode.UNAVAILABLE, retryable=True)] * 10
    now = {"t": datetime.now(UTC)}
    worker = _worker(env, worker_session_factory, clock=lambda: now["t"])

    # Act
    for _ in range(8):
        await worker.process_one()
        now["t"] += timedelta(minutes=10)
    items = (
        await client.get(f"/api/v1/projects/{project_id}/publications", headers=MANAGER)
    ).json()["items"]

    # Assert
    assert (items[0]["status"], items[0]["attempts"]) == ("failed", 5)
    assert env.drive.published == []


async def test_revoked_link_is_not_published_to(
    client: AsyncClient, env: Env, project_id: UUID, worker_session_factory: Factory
) -> None:
    # Arrange
    link = await _link(client, project_id, DRIVE_URL)
    await _publish_now(client, project_id)
    revoked = await client.delete(
        f"/api/v1/projects/{project_id}/links/{link['id']}", headers=MANAGER
    )
    assert revoked.json()["status"] == "revoked"

    # Act
    await _worker(env, worker_session_factory).process_one()
    items = (
        await client.get(f"/api/v1/projects/{project_id}/publications", headers=MANAGER)
    ).json()["items"]

    # Assert
    assert (items[0]["status"], items[0]["error_code"]) == ("failed", "link_unavailable")
    assert env.drive.published == []


async def test_rejected_artifact_is_not_published(
    client: AsyncClient, env: Env, project_id: UUID, worker_session_factory: Factory
) -> None:
    # Arrange: o gerente rejeita o artefato depois de enfileirado
    await _link(client, project_id, DRIVE_URL)
    queued = await _publish_now(client, project_id)
    artifact_id = queued["items"][0]["artifact_id"]
    rejected = await client.post(
        f"/api/v1/artifacts/{artifact_id}/approval", json={"decision": "reject"}, headers=MANAGER
    )
    assert rejected.status_code == 201

    # Act
    await _worker(env, worker_session_factory).process_one()
    items = (
        await client.get(f"/api/v1/projects/{project_id}/publications", headers=MANAGER)
    ).json()["items"]

    # Assert
    assert (items[0]["status"], items[0]["error_code"]) == ("failed", "artifact_not_publishable")
    assert env.drive.published == []


async def test_destination_removed_from_server_config_fails_cleanly(
    client: AsyncClient, env: Env, project_id: UUID, worker_session_factory: Factory
) -> None:
    # Arrange
    await _link(client, project_id, NOTION_URL)
    await _publish_now(client, project_id)
    worker = PublicationWorker(
        factory=worker_session_factory,
        registry=IntegrationRegistry(
            cast(Settings, env.app.state.settings), httpx.AsyncClient(), destinations={}
        ),
        tenant_id=env.tenant_id,
    )

    # Act
    await worker.process_one()
    items = (
        await client.get(f"/api/v1/projects/{project_id}/publications", headers=MANAGER)
    ).json()["items"]

    # Assert
    assert (items[0]["status"], items[0]["error_code"]) == ("failed", "not_configured")


async def test_agent_run_completion_enqueues_publication(
    client: AsyncClient, env: Env, project_id: UUID, worker_session_factory: Factory
) -> None:
    # Arrange: o passo pós-Checker do worker do agente enfileira nos links autorizados
    await _link(client, project_id, DRIVE_URL)
    agent = Worker(
        factory=worker_session_factory,
        client=cast(Any, None),
        verifier=cast(Any, None),
        config=WorkerConfig(tenant_id=env.tenant_id, model=ModelSettings()),
    )

    # Act
    await agent._enqueue_publications(project_id)

    # Assert
    items = (
        await client.get(f"/api/v1/projects/{project_id}/publications", headers=MANAGER)
    ).json()["items"]
    assert [i["status"] for i in items] == ["queued"]


# --- isolamento e privilégios ---


async def test_other_tenant_does_not_see_links_or_publications(
    client: AsyncClient, project_id: UUID, env: Env, session_factory: Factory
) -> None:
    # Arrange
    await _link(client, project_id, DRIVE_URL)
    await _publish_now(client, project_id)
    other = uuid4()

    # Act
    async with tenant_session(session_factory, other) as session:
        service = PublishingService(session)
        links = await service.list_links(other, project_id)
        pubs = await service.list_publications(other, project_id)

    # Assert
    assert links == []
    assert pubs == []


async def test_api_role_cannot_rewrite_publication_results(
    client: AsyncClient, env: Env, project_id: UUID, session_factory: Factory
) -> None:
    # Arrange
    await _link(client, project_id, DRIVE_URL)
    await _publish_now(client, project_id)

    # Act / Assert: só o worker grava o resultado da publicação
    async with tenant_session(session_factory, env.tenant_id) as session:
        with pytest.raises(DBAPIError, match="permission denied"):
            await session.execute(text("UPDATE publications SET status = 'published'"))


async def test_worker_role_cannot_authorize_links(
    env: Env, project_id: UUID, worker_session_factory: Factory
) -> None:
    # Act / Assert: autorizar destino é ação humana (API), nunca do processo do agente
    async with tenant_session(worker_session_factory, env.tenant_id) as session:
        with pytest.raises(DBAPIError, match="permission denied"):
            await session.execute(
                text(
                    "INSERT INTO project_links (id, tenant_id, project_id, kind, url, external_id,"
                    " display_name, created_by) VALUES (gen_random_uuid(), :t, :p, 'drive_folder',"
                    " 'u', 'x', 'n', gen_random_uuid())"
                ),
                {"t": env.tenant_id, "p": project_id},
            )


async def test_links_and_publications_cannot_be_deleted(
    client: AsyncClient, env: Env, project_id: UUID, session_factory: Factory
) -> None:
    # Arrange
    await _link(client, project_id, DRIVE_URL)

    # Act / Assert
    for table in ("project_links", "publications"):
        async with tenant_session(session_factory, env.tenant_id) as session:
            with pytest.raises(DBAPIError, match="permission denied"):
                await session.execute(text(f"DELETE FROM {table}"))  # noqa: S608
