"""Rotas HTTP de versões de relatório (`/api/v1/reports`). Sem regra de negócio."""

from contextlib import AbstractAsyncContextManager
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from basho.db import tenant_session
from basho.identity import HumanIdentity, current_human
from basho.reports.corrections import InvalidCorrectionError
from basho.reports.schemas import ReportVersionOut, ReviewIn, ReviewOut, VersionConflictOut
from basho.reports.service import ReportNotFoundError, ReportService, ReportValidationError
from basho.reports.versions import ReviewerNotAllowedError, ReviewerRole, VersionConflictError

router = APIRouter(prefix="/reports", tags=["reports"])

NOT_FOUND_DETAIL = "relatório não encontrado"
FORBIDDEN_DETAIL = "revisor sem permissão para este papel neste relatório"
INVALID_DETAIL = "revisão ou correção inválida para esta versão"


def _scope(request: Request) -> AbstractAsyncContextManager[AsyncSession]:
    """Transação do tenant (MVP single-tenant). Commit só ao sair do bloco sem erro."""
    return tenant_session(request.app.state.session_factory, request.app.state.settings.tenant_id)


@router.get("/{report_version_id}", response_model=ReportVersionOut)
async def get_report_version(report_version_id: UUID, request: Request) -> ReportVersionOut:
    tenant_id = request.app.state.settings.tenant_id
    try:
        async with _scope(request) as session:
            return await ReportService(session).get_version(tenant_id, report_version_id)
    except ReportNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL) from None


@router.post(
    "/{report_version_id}/review",
    response_model=ReviewOut,
    status_code=status.HTTP_201_CREATED,
    responses={status.HTTP_409_CONFLICT: {"model": VersionConflictOut}},
)
async def review_report_version(
    report_version_id: UUID,
    body: ReviewIn,
    request: Request,
    reviewer: HumanIdentity = Depends(current_human),  # noqa: B008
) -> ReviewOut | JSONResponse:
    """Ação formal, só humano (ADR-0005). Versão que não é a atual → 409, nada gravado."""
    tenant_id = request.app.state.settings.tenant_id
    try:
        async with _scope(request) as session:
            return await ReportService(session).review(
                tenant_id,
                report_version_id,
                body,
                reviewer_id=reviewer.user_id,
                reviewer_role=ReviewerRole(reviewer.role.value),
            )
    except VersionConflictError as conflict:
        payload = VersionConflictOut(
            detail="a versão revisada não é a atual do relatório",
            requested_version_id=conflict.requested_id,
            current_version_id=conflict.current_id,
        )
        return JSONResponse(payload.model_dump(mode="json"), status_code=status.HTTP_409_CONFLICT)
    except ReviewerNotAllowedError:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=FORBIDDEN_DETAIL) from None
    except ReportNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL) from None
    except (ReportValidationError, InvalidCorrectionError):
        # Mensagem fixa: a do domínio pode carregar detalhe interno (ADR-0006 §6).
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=INVALID_DETAIL) from None
