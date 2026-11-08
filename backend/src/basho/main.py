"""App factory FastAPI."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict

from basho.agent.api import router as agent_router
from basho.config import Settings, get_settings
from basho.db import (
    API_ROLE,
    WORKER_ROLE,
    assert_least_privilege,
    assert_process_role,
    create_engine,
    create_session_factory,
)
from basho.evidence.api import router as evidence_router
from basho.logging import configure_logging, get_logger
from basho.projects.api import router as projects_router
from basho.publishing.api import router as publishing_router
from basho.publishing.destinations import IntegrationRegistry
from basho.reports.api import router as reports_router
from basho.reports.project_api import router as report_projects_router

APP_TITLE = "Basho API"
APP_VERSION = "0.1.0"
API_PREFIX = "/api/v1"


class HealthResponse(BaseModel):
    """Resposta do health check."""

    model_config = ConfigDict(frozen=True)

    status: str


def create_app(settings: Settings | None = None) -> FastAPI:
    """Cria a aplicação; valida a configuração antes de qualquer outra coisa (fail fast)."""
    configure_logging()
    resolved = settings if settings is not None else get_settings()
    # create_async_engine não abre conexão: o banco só é tocado na primeira requisição.
    engine = create_engine(resolved.database_url.get_secret_value())
    http = httpx.AsyncClient()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # Aborta o startup se DATABASE_URL for superuser, BYPASSRLS ou dono (ADR-0006, #21).
        await assert_least_privilege(engine)
        # E não pode ser também o login do worker (separação de papéis, ADR-0005).
        await assert_process_role(engine, required=API_ROLE, forbidden=WORKER_ROLE)
        yield
        await http.aclose()
        await engine.dispose()

    app = FastAPI(title=APP_TITLE, version=APP_VERSION, lifespan=lifespan)
    app.state.settings = resolved
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    app.state.integrations = IntegrationRegistry(resolved, http)
    app.include_router(reports_router, prefix=API_PREFIX)
    app.include_router(agent_router, prefix=API_PREFIX)
    app.include_router(report_projects_router, prefix=API_PREFIX)
    app.include_router(evidence_router, prefix=API_PREFIX)
    app.include_router(projects_router, prefix=API_PREFIX)
    app.include_router(publishing_router, prefix=API_PREFIX)

    @app.get("/health", response_model=HealthResponse, tags=["health"])
    async def health() -> HealthResponse:
        return HealthResponse(status="ok")

    get_logger(__name__).info("app_created", tenant_id=str(resolved.tenant_id))
    return app


def app() -> FastAPI:
    """Entry point para ``uvicorn basho.main:app --factory``."""
    return create_app()
