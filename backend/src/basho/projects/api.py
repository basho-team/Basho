"""Rotas HTTP de projetos, pendências, aprovação formal e dossiê (#5). Sem regra de negócio."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from basho.compliance.api_contracts import (
    ApprovalIn,
    ApprovalOut,
    ConflictOut,
    DossierOut,
    PendingAnswerIn,
    PendingAnswerOut,
    PendingPageOut,
    PendingStatus,
    ProjectOut,
)
from basho.db import tenant_session
from basho.evidence.domain.rules import EvidenceValidationError
from basho.identity import HumanIdentity, current_human
from basho.projects.service import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    ProjectConflictError,
    ProjectForbiddenError,
    ProjectNotFoundError,
    ProjectService,
    ProjectViewTooLargeError,
)

router = APIRouter(tags=["projects"])

NOT_FOUND_DETAIL = "recurso não encontrado"
FORBIDDEN_DETAIL = "papel sem permissão para esta ação"
INVALID_DETAIL = "resposta inválida para esta pendência"
TOO_LARGE_DETAIL = "projeto com histórico acima do limite de leitura"
CONFLICT_DETAILS = {
    "approval_via_artifact_endpoint": "pendência de aprovação se resolve na rota de aprovação",
    "pending_closed": "pendência já respondida ou encerrada",
    "already_decided": "artefato já tem decisão formal",
    "artifact_not_verified": "só artefato verificado pode ser aprovado",
    "artifact_not_rejectable": "artefato não pode ser rejeitado neste estado",
    "open_pending": "artefato com pendência aberta",
}
_CONFLICT: dict[int | str, dict[str, Any]] = {status.HTTP_409_CONFLICT: {"model": ConflictOut}}

Human = Annotated[HumanIdentity, Depends(current_human)]
# Leitura também exige a identidade do BFF: dados de projeto não são públicos (#5, MEDIUM 3).
_READ_AUTH = [Depends(current_human)]


@asynccontextmanager
async def _service(request: Request) -> AsyncIterator[ProjectService]:
    """Transação do tenant; traduz erros do domínio em respostas com mensagem fixa."""
    factory = request.app.state.session_factory
    try:
        session: AsyncSession
        async with tenant_session(factory, request.app.state.settings.tenant_id) as session:
            yield ProjectService(session)
    except ProjectNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL) from None
    except ProjectForbiddenError:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=FORBIDDEN_DETAIL) from None
    except ProjectViewTooLargeError:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, detail=TOO_LARGE_DETAIL) from None
    except EvidenceValidationError:
        # Mensagem fixa: a do domínio pode carregar detalhe interno (ADR-0006 §6).
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=INVALID_DETAIL) from None


def _conflict(error: ProjectConflictError) -> JSONResponse:
    body = ConflictOut(
        detail=CONFLICT_DETAILS.get(error.code, "ação inválida no estado atual"),
        code=error.code,
        current_status=error.current_status,
    )
    return JSONResponse(body.model_dump(mode="json"), status_code=status.HTTP_409_CONFLICT)


def _tenant(request: Request) -> UUID:
    tenant_id: UUID = request.app.state.settings.tenant_id
    return tenant_id


@router.get("/projects/{project_id}", response_model=ProjectOut, dependencies=_READ_AUTH)
async def get_project(project_id: UUID, request: Request) -> ProjectOut:
    async with _service(request) as service:
        return await service.get_project(_tenant(request), project_id)


@router.get(
    "/projects/{project_id}/pending", response_model=PendingPageOut, dependencies=_READ_AUTH
)
async def list_pending(
    project_id: UUID,
    request: Request,
    pending_status: Annotated[PendingStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PendingPageOut:
    async with _service(request) as service:
        return await service.list_pending(
            _tenant(request), project_id, status=pending_status, limit=limit, offset=offset
        )


@router.get("/projects/{project_id}/dossier", response_model=DossierOut, dependencies=_READ_AUTH)
async def get_dossier(project_id: UUID, request: Request) -> DossierOut:
    async with _service(request) as service:
        return await service.dossier(_tenant(request), project_id)


@router.post(
    "/pending/{pending_id}/answer",
    response_model=PendingAnswerOut,
    status_code=status.HTTP_201_CREATED,
    responses=_CONFLICT,
)
async def answer_pending(
    pending_id: UUID, body: PendingAnswerIn, request: Request, human: Human
) -> PendingAnswerOut | JSONResponse:
    """Ação humana do papel designado: `user_correction` com `supersedes` = artefato."""
    try:
        async with _service(request) as service:
            return await service.answer(_tenant(request), pending_id, body, human)
    except ProjectConflictError as error:
        return _conflict(error)


@router.post(
    "/artifacts/{artifact_id}/approval",
    response_model=ApprovalOut,
    status_code=status.HTTP_201_CREATED,
    responses=_CONFLICT,
)
async def decide_artifact(
    artifact_id: UUID, body: ApprovalIn, request: Request, human: Human
) -> ApprovalOut | JSONResponse:
    """Ação FORMAL, só humano com papel `manager` (ADR-0005). Nunca exposta ao agente."""
    try:
        async with _service(request) as service:
            return await service.decide(_tenant(request), artifact_id, body, human)
    except ProjectConflictError as error:
        return _conflict(error)
