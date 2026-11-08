"""Cliente mínimo da API do Notion (httpx, sem SDK; integração interna por token).

O usuário compartilha a página com a integração do Basho; o Basho cria, sob ela, a página
``BASHO`` e, dentro dela, uma página por relatório. Antes de criar, lista os filhos e procura pelo
título: reexecutar depois de falha não duplica. Conteúdo vem como blocos de texto simples (nunca
HTML nem markdown interpretado), então texto externo não vira formatação ou link ativo.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import SecretStr

from basho.publishing.clients.errors import ProviderError, ProviderErrorCode, error_from_status
from basho.resilience import RetryPolicy, call_with_retry

API_URL = "https://api.notion.com"
NOTION_VERSION = "2022-06-28"
BASHO_PAGE_TITLE = "BASHO"
MAX_BLOCKS_PER_REQUEST = 100
MAX_RICH_TEXT_CHARS = 1900  # o limite do Notion é 2000 por trecho
MAX_PAGES_SCANNED = 5
DEFAULT_TIMEOUT_SECONDS = 20.0


@dataclass(frozen=True, slots=True)
class NotionPage:
    id: str
    title: str
    url: str


def rich_text(text: str) -> list[dict[str, Any]]:
    """Divide o texto em trechos aceitos pelo Notion; sempre texto puro, sem link."""
    chunks = [text[i : i + MAX_RICH_TEXT_CHARS] for i in range(0, len(text), MAX_RICH_TEXT_CHARS)]
    return [{"type": "text", "text": {"content": chunk}} for chunk in chunks or [""]]


def _is_retryable(exc: Exception) -> bool:
    return isinstance(exc, ProviderError) and exc.retryable


def _title_of(page: dict[str, Any]) -> str:
    properties = page.get("properties")
    if isinstance(properties, dict):
        for prop in properties.values():
            if isinstance(prop, dict) and prop.get("type") == "title":
                parts = prop.get("title")
                if isinstance(parts, list):
                    return "".join(
                        str(p.get("plain_text", "")) for p in parts if isinstance(p, dict)
                    )
    return ""


class NotionClient:
    def __init__(
        self,
        *,
        token: SecretStr,
        http: httpx.AsyncClient,
        api_url: str = API_URL,
        retry: RetryPolicy | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._token = token
        self._http = http
        self._api_url = api_url.rstrip("/")
        self._retry = retry or RetryPolicy(max_attempts=3, base_delay=1.0, max_delay=10.0)
        self._sleep = sleep

    async def _send(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
        repeatable: bool,
    ) -> dict[str, Any]:
        async def once() -> dict[str, Any]:
            try:
                response = await self._http.request(
                    method,
                    f"{self._api_url}{path}",
                    params=params,
                    json=json_body,
                    headers={
                        "Authorization": f"Bearer {self._token.get_secret_value()}",
                        "Notion-Version": NOTION_VERSION,
                    },
                    timeout=DEFAULT_TIMEOUT_SECONDS,
                )
            except httpx.HTTPError:
                raise ProviderError(ProviderErrorCode.UNAVAILABLE, retryable=True) from None
            if response.status_code >= httpx.codes.BAD_REQUEST:
                raise error_from_status(response.status_code)
            try:
                body = response.json()
            except ValueError:
                raise ProviderError(ProviderErrorCode.UNEXPECTED) from None
            if not isinstance(body, dict):
                raise ProviderError(ProviderErrorCode.UNEXPECTED)
            return body

        if not repeatable:
            return await once()
        return await call_with_retry(
            once, policy=self._retry, is_retryable=_is_retryable, sleep=self._sleep
        )

    async def get_page(self, page_id: str) -> NotionPage:
        """404 aqui quase sempre significa 'a página não foi compartilhada com a integração'."""
        body = await self._send("GET", f"/v1/pages/{page_id}", repeatable=True)
        return NotionPage(
            id=str(body.get("id", page_id)), title=_title_of(body), url=str(body.get("url", ""))
        )

    async def _find_child_page(self, parent_id: str, title: str) -> str | None:
        cursor: str | None = None
        for _ in range(MAX_PAGES_SCANNED):
            params = {"page_size": "100", **({"start_cursor": cursor} if cursor else {})}
            body = await self._send(
                "GET", f"/v1/blocks/{parent_id}/children", params=params, repeatable=True
            )
            results = body.get("results")
            for block in results if isinstance(results, list) else []:
                child = block.get("child_page") if isinstance(block, dict) else None
                if isinstance(child, dict) and child.get("title") == title:
                    return str(block["id"])
            next_cursor = body.get("next_cursor")
            if not body.get("has_more") or not isinstance(next_cursor, str):
                return None
            cursor = next_cursor
        return None

    async def _create_page(
        self, parent_id: str, title: str, blocks: Sequence[dict[str, Any]]
    ) -> NotionPage:
        first, rest = list(blocks[:MAX_BLOCKS_PER_REQUEST]), list(blocks[MAX_BLOCKS_PER_REQUEST:])
        body = await self._send(
            "POST",
            "/v1/pages",
            json_body={
                "parent": {"page_id": parent_id},
                "properties": {"title": {"title": rich_text(title)}},
                "children": first,
            },
            repeatable=False,
        )
        page_id = str(body["id"])
        while rest:
            batch, rest = rest[:MAX_BLOCKS_PER_REQUEST], rest[MAX_BLOCKS_PER_REQUEST:]
            await self._send(
                "PATCH",
                f"/v1/blocks/{page_id}/children",
                json_body={"children": batch},
                repeatable=False,
            )
        return NotionPage(id=page_id, title=title, url=str(body.get("url", "")))

    async def ensure_page(self, parent_id: str, title: str = BASHO_PAGE_TITLE) -> str:
        existing = await self._find_child_page(parent_id, title)
        if existing is not None:
            return existing
        return (await self._create_page(parent_id, title, [])).id

    async def create_report_page(
        self, parent_id: str, title: str, blocks: Sequence[dict[str, Any]]
    ) -> NotionPage:
        """Cria a página do relatório; se já houver filha com o título, reutiliza."""
        existing = await self._find_child_page(parent_id, title)
        if existing is not None:
            page = await self.get_page(existing)
            return NotionPage(id=page.id, title=title, url=page.url)
        return await self._create_page(parent_id, title, blocks)
