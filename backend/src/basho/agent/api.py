"""Rotas HTTP de runs do agente (`/api/v1`). Sem regra de negócio (ADR-0001).

`POST /projects/{id}/agent-runs`: um humano identificado dispara (só enfileira) e recebe o
`run_id`. `GET /agent-runs/{id}`: estado de execução, erro resumido e custo/latência por chamada.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from basho.agent.artifacts import ReportingPeriod
from basho.agent.run_service import AgentRunService, ResearchReportRequest, RunDetails
from basho.agent.run_store import RunNotFoundError
from basho.agent.runs import IDEMPOTENCY_KEY_PATTERN, RunError, RunStatus
from basho.db import tenant_session
from basho.reports.api import Reviewer, current_reviewer

router = APIRouter(tags=["agent"])

NOT_FOUND_DETAIL = "run não encontrado"
INVALID_DETAIL = "tarefa inválida para este projeto"
IDEMPOTENCY_HEADER = "Idempotency-Key"


class AgentRunIn(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    task_kind: Literal["research_report"] = "research_report"
    researcher_id: UUID
    period: ReportingPeriod


class AgentCallOut(BaseModel):
    attempt: int
    model: str
    prompt_version: str
    stop_reason: str | None
    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int
    cache_creation_input_tokens: int
    latency_ms: int
    estimated_cost_usd: Decimal | None


class AgentRunOut(BaseModel):
    id: UUID
    project_id: UUID
    task_kind: str
    prompt_version: str
    status: RunStatus
    attempts: int
    max_attempts: int
    error: RunError | None
    run_after: datetime
    created_at: datetime
    updated_at: datetime
    artifact_event_id: UUID | None
    verification_event_id: UUID | None
    artifact_status: str | None
    calls: list[AgentCallOut] = Field(default_factory=list)
    total_latency_ms: int
    total_estimated_cost_usd: Decimal | None


def _out(details: RunDetails) -> AgentRunOut:
    stored, run = details.stored, details.stored.run
    return AgentRunOut(
        id=run.id,
        project_id=stored.project_id,
        task_kind=run.task_kind.value,
        prompt_version=run.prompt_version,
        status=run.status,
        attempts=run.attempts,
        max_attempts=run.max_attempts,
        error=run.error,
        run_after=stored.run_after,
        created_at=run.created_at,
        updated_at=run.updated_at,
        artifact_event_id=stored.artifact_event_id,
        verification_event_id=stored.verification_event_id,
        artifact_status=stored.artifact_status,
        calls=[
            AgentCallOut(
                attempt=call.attempt,
                **call.record.model_dump(exclude={"request_id"}),
                estimated_cost_usd=call.estimated_cost_usd,
            )
            for call in details.calls
        ],
        total_latency_ms=sum(call.record.latency_ms for call in details.calls),
        total_estimated_cost_usd=details.total_cost_usd,
    )


def _tenant(request: Request) -> UUID:
    tenant_id: UUID = request.app.state.settings.tenant_id
    return tenant_id


@router.post(
    "/projects/{project_id}/agent-runs",
    response_model=AgentRunOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_agent_run(
    project_id: UUID,
    body: AgentRunIn,
    request: Request,
    response: Response,
    requester: Reviewer = Depends(current_reviewer),  # noqa: B008
    idempotency_key: str | None = Header(
        default=None, alias=IDEMPOTENCY_HEADER, pattern=IDEMPOTENCY_KEY_PATTERN
    ),
) -> AgentRunOut:
    """Humano dispara; o worker executa. Mesma `Idempotency-Key` → o mesmo run (200)."""
    tenant_id = _tenant(request)
    run_request = ResearchReportRequest(
        project_id=project_id,
        researcher_id=body.researcher_id,
        period=body.period,
        requested_by=requester.user_id,
        idempotency_key=idempotency_key,
    )
    try:
        async with tenant_session(request.app.state.session_factory, tenant_id) as session:
            service = AgentRunService(session)
            stored, created = await service.request_research_report(tenant_id, run_request)
            details = await service.get(tenant_id, stored.run.id)
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=INVALID_DETAIL) from None
    if not created:
        response.status_code = status.HTTP_200_OK
    return _out(details)


@router.get("/agent-runs/{run_id}", response_model=AgentRunOut)
async def get_agent_run(run_id: UUID, request: Request) -> AgentRunOut:
    tenant_id = _tenant(request)
    try:
        async with tenant_session(request.app.state.session_factory, tenant_id) as session:
            details = await AgentRunService(session).get(tenant_id, run_id)
    except RunNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL) from None
    return _out(details)
