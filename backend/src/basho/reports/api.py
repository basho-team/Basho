"""Rotas HTTP de versões de relatório (`/api/v1/reports`). Sem regra de negócio."""

import hmac
from contextlib import AbstractAsyncContextManager
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from basho.db import tenant_session
from basho.reports.corrections import InvalidCorrectionError
from basho.reports.schemas import ReportVersionOut, ReviewIn, ReviewOut, VersionConflictOut
from basho.reports.service import ReportNotFoundError, ReportService, ReportValidationError
from basho.reports.versions import ReviewerNotAllowedError, ReviewerRole, VersionConflictError

router = APIRouter(prefix="/reports", tags=["reports"])

USER_ID_HEADER = "X-Basho-User-Id"
ROLE_HEADER = "X-Basho-Role"
IDENTITY_SECRET_HEADER = "X-Basho-Identity-Secret"  # noqa: S105 -- nome do header
NOT_FOUND_DETAIL = "relatório não encontrado"
FORBIDDEN_DETAIL = "revisor sem permissão para este papel neste relatório"
INVALID_DETAIL = "revisão ou correção inválida para esta versão"
UNAUTHORIZED_DETAIL = "identidade do revisor ausente ou não confiável"
UNAVAILABLE_DETAIL = "revisão indisponível: identidade do revisor não configurada"


class Reviewer(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: UUID
    role: ReviewerRole


def _configured_secret(request: Request) -> str:
    secret: SecretStr | None = request.app.state.settings.reviewer_identity_secret
    value = "" if secret is None else secret.get_secret_value()
    if not value:  # vazio conta como ausente: nunca aceitar header vazio
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=UNAVAILABLE_DETAIL)
    return value


def current_reviewer(
    request: Request,
    user_id: str | None = Header(default=None, alias=USER_ID_HEADER),
    role: str | None = Header(default=None, alias=ROLE_HEADER),
    identity_secret: str | None = Header(default=None, alias=IDENTITY_SECRET_HEADER),
) -> Reviewer:
    """PLACEHOLDER de identidade até existir autenticação real (#47).

    Só aceita `X-Basho-User-Id`/`X-Basho-Role` vindos do BFF que conhece
    `REVIEWER_IDENTITY_SECRET` (comparação em tempo constante). Sem segredo configurado, a
    revisão fica fechada (503). A identidade é *afirmada* pelo BFF, não verificada aqui;
    por isso o evento do ledger grava ``identity_verified: false``.
    """
    expected = _configured_secret(request)
    provided = identity_secret or ""
    if not hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=UNAUTHORIZED_DETAIL)
    try:
        if user_id is None or role is None:
            raise ValueError
        return Reviewer(user_id=UUID(user_id), role=ReviewerRole(role))
    except ValueError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=UNAUTHORIZED_DETAIL) from None


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
    reviewer: Reviewer = Depends(current_reviewer),  # noqa: B008
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
                reviewer_role=reviewer.role,
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
