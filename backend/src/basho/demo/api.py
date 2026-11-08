"""`GET /api/v1/demo/context`: contexto sintético da demonstração."""

from fastapi import APIRouter

from basho.demo.context import DemoContext

router = APIRouter(prefix="/demo", tags=["demo"])


@router.get("/context", response_model=DemoContext)
async def demo_context() -> DemoContext:
    return DemoContext()
