"""Rotas de relatórios por projeto/período: listar, rascunho automático e consolidação.

Sem regra de negócio: `ReportQueryService` e o domínio puro. Toda rota exige a identidade do
BFF (`current_human`), inclusive as leituras, como em `reports/api.py` e `projects/api.py`.
"""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from basho.agent.artifacts import Periodicity, ReportingPeriod
from basho.identity import HumanIdentity, HumanRole, current_human
from basho.reports.api import _scope
from basho.reports.auto_draft import NothingToDraftError
from basho.reports.consolidation import ManagerConsolidation, consolidate
from basho.reports.narrative import render_manager_summary
from basho.reports.schemas import PeriodClosingOut, ReportReviewFlag, ReportVersionOut
from basho.reports.service import ReportQueryService

router = APIRouter(prefix="/projects", tags=["reports"])

NO_EVIDENCE_DETAIL = "nenhuma evidência sua no período para gerar o rascunho"


def period_query(
    start: Annotated[date, Query()],
    end: Annotated[date, Query()],
    timezone: Annotated[str, Query()] = "America/Sao_Paulo",
    periodicity: Annotated[Periodicity, Query()] = Periodicity.MONTHLY,
) -> ReportingPeriod:
    try:
        return ReportingPeriod(start=start, end=end, timezone=timezone, periodicity=periodicity)
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "período inválido") from None


Period = Annotated[ReportingPeriod, Depends(period_query)]
Human = Annotated[HumanIdentity, Depends(current_human)]


class ConsolidationOut(BaseModel):
    """`consolidation` é calculada na leitura a partir das versões atuais (não persistida)."""

    model_config = ConfigDict(frozen=True)
    consolidation: ManagerConsolidation | None
    summary_markdown: str | None
    needs_review: list[ReportReviewFlag] = Field(
        default_factory=list, description="Relatórios afetados por correção de evidência (#11)"
    )


@router.get("/{project_id}/reports", response_model=list[ReportVersionOut])
async def list_reports(
    project_id: UUID, period: Period, request: Request, _: Human
) -> list[ReportVersionOut]:
    """Versão atual de cada relatório do projeto no período, com estado de revisão por papel."""
    async with _scope(request) as session:
        return await ReportQueryService(session).list_current(
            request.app.state.settings.tenant_id, project_id, period
        )


@router.post(
    "/{project_id}/reports/auto-draft",
    response_model=ReportVersionOut,
    status_code=status.HTTP_201_CREATED,
)
async def auto_draft(
    project_id: UUID, period: Period, request: Request, human: Human
) -> ReportVersionOut:
    """Rascunho do próprio pesquisador, por regras (sem LLM); devolve o atual se já existir."""
    if human.role is not HumanRole.RESEARCHER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "só o pesquisador gera o próprio rascunho")
    try:
        async with _scope(request) as session:
            return await ReportQueryService(session).auto_draft(
                request.app.state.settings.tenant_id, project_id, human.user_id, period
            )
    except NothingToDraftError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NO_EVIDENCE_DETAIL) from None


@router.get("/{project_id}/consolidation", response_model=ConsolidationOut)
async def get_consolidation(
    project_id: UUID, period: Period, request: Request, _: Human
) -> ConsolidationOut:
    tenant_id = request.app.state.settings.tenant_id
    async with _scope(request) as session:
        query = ReportQueryService(session)
        inputs = await query.project_inputs(tenant_id, project_id, period)
        flags = await query.needs_review(tenant_id, project_id, period)
    if not inputs:
        return ConsolidationOut(consolidation=None, summary_markdown=None)
    consolidation = consolidate(inputs)
    return ConsolidationOut(
        consolidation=consolidation,
        summary_markdown=render_manager_summary(consolidation),
        needs_review=flags,
    )


@router.get("/{project_id}/reports/needs-review", response_model=list[ReportReviewFlag])
async def reports_needing_review(
    project_id: UUID, period: Period, request: Request, _: Human
) -> list[ReportReviewFlag]:
    async with _scope(request) as session:
        return await ReportQueryService(session).needs_review(
            request.app.state.settings.tenant_id, project_id, period
        )


@router.post("/{project_id}/period/close", response_model=PeriodClosingOut)
async def close_period(
    project_id: UUID, period: Period, request: Request, human: Human
) -> PeriodClosingOut:
    """Gerente fecha o período: o sistema prepara o rascunho de quem ainda não tem relatório."""
    if human.role is not HumanRole.MANAGER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "só a coordenação fecha o período")
    async with _scope(request) as session:
        return await ReportQueryService(session).close_period(
            request.app.state.settings.tenant_id, project_id, period
        )
