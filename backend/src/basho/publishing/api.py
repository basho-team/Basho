"""Rotas HTTP de links autorizados e publicações (ADR-0010). Sem regra de negócio.

Colar um link autoriza o Basho a ler (GitHub) ou escrever (Drive/Notion) naquele destino. A
autorização é ação de gerente; a leitura e o "publicar agora" valem para qualquer humano
identificado pelo BFF (mesmos headers `X-Basho-*` das demais rotas).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from basho.db import tenant_session
from basho.identity import HumanIdentity, HumanRole, current_human
from basho.projects import ProjectService
from basho.projects.service import ProjectNotFoundError
from basho.publishing.clients.errors import ProviderError, ProviderErrorCode
from basho.publishing.contracts import (
    IntegrationsConfigOut,
    LinkErrorOut,
    LinkIn,
    LinkOut,
    PublicationsOut,
)
from basho.publishing.destinations import IntegrationRegistry
from basho.publishing.links import InvalidLinkError, LinkKind, parse_link
from basho.publishing.service import PublishingService

router = APIRouter(tags=["publishing"])

NOT_FOUND_DETAIL = "recurso não encontrado"
FORBIDDEN_DETAIL = "só o gerente autoriza ou revoga links"
Human = Annotated[HumanIdentity, Depends(current_human)]
_READ_AUTH = [Depends(current_human)]

_SHARE_HINTS = {
    LinkKind.DRIVE_FOLDER: "Compartilhe a pasta como Editor com {email} e cole o link de novo.",
    LinkKind.NOTION_PAGE: (
        "Na página do Notion, abra ••• → Conexões e adicione a integração do Basho."
    ),
    LinkKind.GITHUB_REPO: "Repositório não encontrado ou sem acesso para o token do Basho.",
}


def _registry(request: Request) -> IntegrationRegistry:
    registry: IntegrationRegistry = request.app.state.integrations
    return registry


@asynccontextmanager
async def _scope(request: Request) -> AsyncIterator[AsyncSession]:
    settings = request.app.state.settings
    try:
        async with tenant_session(request.app.state.session_factory, settings.tenant_id) as session:
            yield session
    except ProjectNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL) from None


def _tenant(request: Request) -> UUID:
    tenant_id: UUID = request.app.state.settings.tenant_id
    return tenant_id


def _link_error(
    kind: LinkKind, error: ProviderError, registry: IntegrationRegistry
) -> JSONResponse:
    """Mensagem fixa e acionável; o corpo da resposta do provedor nunca é repassado."""
    code = error.code
    if code is ProviderErrorCode.NOT_CONFIGURED:
        body = LinkErrorOut(
            detail="Esta integração não está configurada no servidor do Basho.", code=code.value
        )
        return JSONResponse(body.model_dump(), status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
    if code in (ProviderErrorCode.RATE_LIMITED, ProviderErrorCode.UNAVAILABLE):
        body = LinkErrorOut(
            detail="O serviço externo não respondeu agora. Tente de novo em instantes.",
            code="provider_unavailable",
        )
        return JSONResponse(body.model_dump(), status_code=status.HTTP_502_BAD_GATEWAY)
    if code is ProviderErrorCode.NOT_A_FOLDER:
        body = LinkErrorOut(detail="O link não é de uma pasta.", code=code.value)
    else:
        hint = _SHARE_HINTS[kind].format(email=registry.service_account_email or "a conta do Basho")
        body = LinkErrorOut(
            detail=f"O Basho não consegue acessar este link. {hint}", code="access_denied"
        )
    return JSONResponse(body.model_dump(), status_code=status.HTTP_422_UNPROCESSABLE_CONTENT)


@router.get("/integrations/config", response_model=IntegrationsConfigOut, dependencies=_READ_AUTH)
async def integrations_config(request: Request) -> IntegrationsConfigOut:
    registry = _registry(request)
    flags = registry.configured()
    return IntegrationsConfigOut(
        drive=flags["drive"],
        notion=flags["notion"],
        github=flags["github"],
        google_service_account_email=registry.service_account_email,
    )


@router.get("/projects/{project_id}/links", response_model=list[LinkOut], dependencies=_READ_AUTH)
async def list_links(project_id: UUID, request: Request) -> list[LinkOut]:
    async with _scope(request) as session:
        await ProjectService(session).get_project(_tenant(request), project_id)
        return await PublishingService(session).list_links(_tenant(request), project_id)


@router.post(
    "/projects/{project_id}/links",
    response_model=LinkOut,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": LinkErrorOut},
        status.HTTP_502_BAD_GATEWAY: {"model": LinkErrorOut},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": LinkErrorOut},
    },
)
async def add_link(
    project_id: UUID, body: LinkIn, request: Request, human: Human
) -> LinkOut | JSONResponse:
    """Autoriza o Basho a usar o link: só gerente; o acesso é verificado antes de gravar."""
    if human.role is not HumanRole.MANAGER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=FORBIDDEN_DETAIL)
    try:
        parsed = parse_link(body.url)
    except InvalidLinkError as error:
        invalid = LinkErrorOut(detail=str(error), code="invalid_link")
        return JSONResponse(invalid.model_dump(), status_code=status.HTTP_422_UNPROCESSABLE_CONTENT)
    tenant_id = _tenant(request)
    async with _scope(request) as session:
        await ProjectService(session).get_project(tenant_id, project_id)
    registry = _registry(request)
    try:
        display_name = await registry.check(parsed.kind, parsed.external_id)
    except ProviderError as error:
        return _link_error(parsed.kind, error, registry)
    async with _scope(request) as session:
        return await PublishingService(session).add_link(
            tenant_id,
            project_id,
            parsed,
            display_name=display_name,
            created_by=human.user_id,
        )


@router.delete("/projects/{project_id}/links/{link_id}", response_model=LinkOut)
async def revoke_link(project_id: UUID, link_id: UUID, request: Request, human: Human) -> LinkOut:
    if human.role is not HumanRole.MANAGER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=FORBIDDEN_DETAIL)
    async with _scope(request) as session:
        revoked = await PublishingService(session).revoke_link(
            _tenant(request), project_id, link_id
        )
    if revoked is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)
    return revoked


@router.get(
    "/projects/{project_id}/publications", response_model=PublicationsOut, dependencies=_READ_AUTH
)
async def list_publications(project_id: UUID, request: Request) -> PublicationsOut:
    async with _scope(request) as session:
        await ProjectService(session).get_project(_tenant(request), project_id)
        items = await PublishingService(session).list_publications(_tenant(request), project_id)
    return PublicationsOut(queued=0, items=tuple(items))


@router.post(
    "/projects/{project_id}/publications",
    response_model=PublicationsOut,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=_READ_AUTH,
)
async def publish_now(project_id: UUID, request: Request) -> PublicationsOut:
    """Enfileira o que está verificado e ainda não publicado; o worker escreve nos destinos."""
    async with _scope(request) as session:
        service = PublishingService(session)
        await ProjectService(session).get_project(_tenant(request), project_id)
        queued = await service.enqueue(_tenant(request), project_id)
        items = await service.list_publications(_tenant(request), project_id)
    return PublicationsOut(queued=queued, items=tuple(items))
