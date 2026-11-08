"""App factory FastAPI."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict

from basho.compliance.api import router as compliance_router
from basho.config import Settings, get_settings
from basho.db import assert_least_privilege, create_engine, create_session_factory
from basho.demo.api import router as demo_router
from basho.evidence.api import router as evidence_router
from basho.logging import configure_logging, get_logger
from basho.reports.api import router as reports_router
from basho.reports.journey_api import router as journey_router

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

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # Aborta o startup se DATABASE_URL for superuser, BYPASSRLS ou dono (ADR-0006, #21).
        await assert_least_privilege(engine)
        yield
        await engine.dispose()

    app = FastAPI(title=APP_TITLE, version=APP_VERSION, lifespan=lifespan)
    app.state.settings = resolved
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    # journey antes de reports: `/reports` (POST) e `/reports/{id}/history` não colidem com
    # `/reports/{id}`, mas a ordem explícita evita surpresa com rotas futuras.
    app.include_router(journey_router, prefix=API_PREFIX)
    app.include_router(reports_router, prefix=API_PREFIX)
    app.include_router(evidence_router, prefix=API_PREFIX)
    app.include_router(compliance_router, prefix=API_PREFIX)
    app.include_router(demo_router, prefix=API_PREFIX)

    @app.get("/health", response_model=HealthResponse, tags=["health"])
    async def health() -> HealthResponse:
        return HealthResponse(status="ok")

    get_logger(__name__).info("app_created", tenant_id=str(resolved.tenant_id))
    return app


def app() -> FastAPI:
    """Entry point para ``uvicorn basho.main:app --factory``."""
    return create_app()
