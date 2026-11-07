"""App factory FastAPI."""

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict

from basho.config import Settings, get_settings
from basho.logging import configure_logging, get_logger

APP_TITLE = "Basho API"
APP_VERSION = "0.1.0"


class HealthResponse(BaseModel):
    """Resposta do health check."""

    model_config = ConfigDict(frozen=True)

    status: str


def create_app(settings: Settings | None = None) -> FastAPI:
    """Cria a aplicação; valida a configuração antes de qualquer outra coisa (fail fast)."""
    configure_logging()
    resolved = settings if settings is not None else get_settings()

    app = FastAPI(title=APP_TITLE, version=APP_VERSION)
    app.state.settings = resolved

    @app.get("/health", response_model=HealthResponse, tags=["health"])
    async def health() -> HealthResponse:
        return HealthResponse(status="ok")

    get_logger(__name__).info("app_created", tenant_id=resolved.tenant_id)
    return app


def app() -> FastAPI:
    """Entry point para ``uvicorn basho.main:app --factory``."""
    return create_app()
