"""`GET /api/v1/demo/context`: contexto sintético da demonstração + disponibilidade real da IA."""

from fastapi import APIRouter, Request

from basho.demo.context import DemoContext

router = APIRouter(prefix="/demo", tags=["demo"])

NOT_CONFIGURED = frozenset({"", "not-configured"})


def _configured(value: str) -> bool:
    return value.strip().lower() not in NOT_CONFIGURED


@router.get("/context", response_model=DemoContext)
async def demo_context(request: Request) -> DemoContext:
    """A IA só aparece como disponível se as chaves estiverem de fato configuradas.

    Mesmo configurada, esta demo ainda não dispara o Maker pela interface (ver docs/demo-local.md).
    """
    settings = request.app.state.settings
    maker = _configured(settings.anthropic_api_key.get_secret_value())
    checker = _configured(settings.featherless_api_key.get_secret_value())
    return DemoContext(ai_maker_available=maker, ai_checker_available=checker)
