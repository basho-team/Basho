"""Rotas da jornada sobre relatórios: criar v1, listar, histórico, checks e consolidação.

Sem regra de negócio: tudo vem de `ReportService`/`ReportQueryService` e do domínio puro.
"""

from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from basho.agent.artifacts import Periodicity, ReportingPeriod, ResearchReportDraft
from basho.agent.verifier import VerificationResult
from basho.evidence.contracts import EventSource
from basho.reports.api import NOT_FOUND_DETAIL, Reviewer, _scope, current_reviewer
from basho.reports.consolidation import ManagerConsolidation, consolidate
from basho.reports.narrative import render_manager_summary
from basho.reports.schemas import ReportVersionOut
from basho.reports.service import (
    ReportAlreadyExistsError,
    ReportNotFoundError,
    ReportQueryService,
    ReportService,
    ReportValidationError,
    _user_actor,
)
from basho.reports.versions import ReviewerRole

router = APIRouter(tags=["journey"])

CHECKER_UNAVAILABLE = (
    "Checker por LLM indisponível neste ambiente: sem chave de API configurada (sem custo "
    "adicional). Só os checks determinísticos foram executados."
)


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
CurrentReviewer = Annotated[Reviewer, Depends(current_reviewer)]


class AlreadyExistsOut(BaseModel):
    model_config = ConfigDict(frozen=True)
    detail: str
    current_version_id: UUID


class ChecksOut(BaseModel):
    model_config = ConfigDict(frozen=True)
    deterministic: VerificationResult
    checker_status: Literal["unavailable"] = "unavailable"
    checker_detail: str = CHECKER_UNAVAILABLE


class ConsolidationOut(BaseModel):
    model_config = ConfigDict(frozen=True)
    consolidation: ManagerConsolidation | None
    summary_markdown: str | None


@router.post(
    "/reports",
    response_model=ReportVersionOut,
    status_code=status.HTTP_201_CREATED,
    responses={status.HTTP_409_CONFLICT: {"model": AlreadyExistsOut}},
)
async def create_report(
    draft: ResearchReportDraft, request: Request, reviewer: CurrentReviewer
) -> ReportVersionOut | JSONResponse:
    """Pesquisador cria a v1 do próprio relatório (ação humana, citações conferidas)."""
    if reviewer.role is not ReviewerRole.RESEARCHER or reviewer.user_id != draft.researcher_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "só o próprio pesquisador cria o relatório")
    settings = request.app.state.settings
    try:
        async with _scope(request) as session:
            return await ReportService(session).create_report(
                settings.tenant_id,
                draft,
                actor=_user_actor(reviewer.user_id),
                source=EventSource.USER,
                is_synthetic=True,
            )
    except ReportAlreadyExistsError as exists:
        payload = AlreadyExistsOut(
            detail="já existe relatório deste pesquisador no período; corrija a versão atual",
            current_version_id=exists.current_version_id,
        )
        return JSONResponse(payload.model_dump(mode="json"), status_code=status.HTTP_409_CONFLICT)
    except ReportValidationError as invalid:
        # Mensagens do serviço de criação são fixas e sem dado interno (citações/horas).
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(invalid)) from None


@router.get("/projects/{project_id}/reports", response_model=list[ReportVersionOut])
async def list_reports(
    project_id: UUID, period: Period, request: Request
) -> list[ReportVersionOut]:
    async with _scope(request) as session:
        return await ReportQueryService(session).list_current(
            request.app.state.settings.tenant_id, project_id, period
        )


@router.get("/reports/{report_version_id}/history", response_model=list[ReportVersionOut])
async def report_history(report_version_id: UUID, request: Request) -> list[ReportVersionOut]:
    try:
        async with _scope(request) as session:
            return await ReportQueryService(session).history(
                request.app.state.settings.tenant_id, report_version_id
            )
    except ReportNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND_DETAIL) from None


@router.post("/reports/{report_version_id}/checks", response_model=ChecksOut)
async def run_checks(report_version_id: UUID, request: Request) -> ChecksOut:
    try:
        async with _scope(request) as session:
            result = await ReportQueryService(session).run_checks(
                request.app.state.settings.tenant_id, report_version_id
            )
    except ReportNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND_DETAIL) from None
    return ChecksOut(deterministic=result)


@router.get("/projects/{project_id}/consolidation", response_model=ConsolidationOut)
async def get_consolidation(project_id: UUID, period: Period, request: Request) -> ConsolidationOut:
    async with _scope(request) as session:
        inputs = await ReportQueryService(session).project_inputs(
            request.app.state.settings.tenant_id, project_id, period
        )
    if not inputs:
        return ConsolidationOut(consolidation=None, summary_markdown=None)
    consolidation = consolidate(inputs)
    return ConsolidationOut(
        consolidation=consolidation, summary_markdown=render_manager_summary(consolidation)
    )
