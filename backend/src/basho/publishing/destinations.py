"""Destinos de publicação (Drive, Notion) e verificação das fontes (GitHub) atrás de um registro.

O resto do código só conhece `Destination`: troca-se por um fake nos testes e a credencial real
fica confinada aqui (lida das variáveis de ambiente, ADR-0006).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx

from basho.config import Settings
from basho.connectors.github import GithubClient, GithubError, GithubErrorCode, RepoRef
from basho.publishing.clients.drive import API_URL as DRIVE_API_URL
from basho.publishing.clients.drive import DriveClient
from basho.publishing.clients.errors import ProviderError, ProviderErrorCode
from basho.publishing.clients.google_auth import (
    TOKEN_URI,
    ServiceAccountInfo,
    ServiceAccountTokens,
)
from basho.publishing.clients.notion import API_URL as NOTION_API_URL
from basho.publishing.clients.notion import NotionClient
from basho.publishing.links import LinkKind
from basho.publishing.render import RenderedDoc


@dataclass(frozen=True, slots=True)
class PublishedDoc:
    external_id: str
    url: str


class Destination(Protocol):
    kind: LinkKind

    async def check(self, external_id: str) -> str:
        """Confirma que o Basho consegue escrever; devolve o nome legível. Levanta ProviderError."""
        ...

    async def publish(self, external_id: str, doc: RenderedDoc) -> PublishedDoc: ...


class DriveDestination:
    kind = LinkKind.DRIVE_FOLDER

    def __init__(self, client: DriveClient) -> None:
        self._client = client

    async def check(self, external_id: str) -> str:
        folder = await self._client.get_folder(external_id)
        if not folder.can_add_children:
            raise ProviderError(ProviderErrorCode.ACCESS_DENIED)
        return folder.name or "Pasta do Google Drive"

    async def publish(self, external_id: str, doc: RenderedDoc) -> PublishedDoc:
        basho_folder = await self._client.ensure_folder(external_id)
        created = await self._client.create_document(basho_folder, doc.title, doc.to_html())
        return PublishedDoc(external_id=created.id, url=created.url)


class NotionDestination:
    kind = LinkKind.NOTION_PAGE

    def __init__(self, client: NotionClient) -> None:
        self._client = client

    async def check(self, external_id: str) -> str:
        page = await self._client.get_page(external_id)
        return page.title or "Página do Notion"

    async def publish(self, external_id: str, doc: RenderedDoc) -> PublishedDoc:
        basho_page = await self._client.ensure_page(external_id)
        page = await self._client.create_report_page(basho_page, doc.title, doc.to_notion_blocks())
        return PublishedDoc(external_id=page.id, url=page.url)


_GITHUB_TO_PROVIDER = {
    GithubErrorCode.UNAUTHORIZED: ProviderErrorCode.UNAUTHORIZED,
    GithubErrorCode.NOT_FOUND: ProviderErrorCode.NOT_FOUND,
    GithubErrorCode.RATE_LIMITED: ProviderErrorCode.RATE_LIMITED,
}


class IntegrationRegistry:
    """Monta os clientes a partir das variáveis de ambiente; ausência vira NOT_CONFIGURED."""

    def __init__(
        self,
        settings: Settings,
        http: httpx.AsyncClient,
        *,
        destinations: dict[LinkKind, Destination] | None = None,
        github: GithubClient | None = None,
    ) -> None:
        self._http = http
        self._destinations: dict[LinkKind, Destination] = (
            destinations if destinations is not None else {}
        )
        self._github = github
        self.service_account_email: str | None = None
        if destinations is None:
            self._build(settings)

    def _build(self, settings: Settings) -> None:
        raw = settings.google_service_account_json
        if raw is not None and raw.get_secret_value().strip():
            try:
                info = ServiceAccountInfo.parse(raw.get_secret_value())
            except ProviderError:
                info = None
            if info is not None:
                token_uri = settings.google_token_uri
                tokens = ServiceAccountTokens(
                    info, self._http, token_uri=str(token_uri) if token_uri else TOKEN_URI
                )
                self.service_account_email = tokens.email
                drive_url = settings.google_drive_api_url
                self._destinations[LinkKind.DRIVE_FOLDER] = DriveDestination(
                    DriveClient(
                        tokens=tokens,
                        http=self._http,
                        api_url=str(drive_url) if drive_url else DRIVE_API_URL,
                    )
                )
        notion = settings.notion_token
        if notion is not None and notion.get_secret_value().strip():
            notion_url = settings.notion_api_url
            self._destinations[LinkKind.NOTION_PAGE] = NotionDestination(
                NotionClient(
                    token=notion,
                    http=self._http,
                    api_url=str(notion_url) if notion_url else NOTION_API_URL,
                )
            )
        if self._github is None and settings.github_token.get_secret_value().strip():
            self._github = GithubClient(token=settings.github_token, http_client=self._http)

    def destination(self, kind: LinkKind) -> Destination | None:
        return self._destinations.get(kind)

    def configured(self) -> dict[str, bool]:
        return {
            "drive": LinkKind.DRIVE_FOLDER in self._destinations,
            "notion": LinkKind.NOTION_PAGE in self._destinations,
            "github": self._github is not None,
        }

    async def check(self, kind: LinkKind, external_id: str) -> str:
        """Confirma o acesso do Basho ao link; devolve o nome legível ou levanta ProviderError."""
        if kind is LinkKind.GITHUB_REPO:
            if self._github is None:
                raise ProviderError(ProviderErrorCode.NOT_CONFIGURED)
            try:
                await self._github.list_commits(RepoRef(external_id), limit=1)
            except GithubError as exc:
                code = _GITHUB_TO_PROVIDER.get(exc.code, ProviderErrorCode.UNAVAILABLE)
                raise ProviderError(code, retryable=exc.retryable) from None
            return external_id
        destination = self._destinations.get(kind)
        if destination is None:
            raise ProviderError(ProviderErrorCode.NOT_CONFIGURED)
        return await destination.check(external_id)
