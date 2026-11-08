"""Cliente mínimo da API do Notion, só leitura (ADR-0010).

Auth: token de integração interna (`NOTION_TOKEN`); a integração só enxerga o que foi
compartilhado com ela no workspace. Lê páginas de databases (editadas desde `since`) e páginas
avulsas. O texto vem dos blocos de primeiro nível (`rich_text.plain_text`); a revisão é o
`last_edited_time` da página.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
from pydantic import SecretStr

from basho.connectors.documents import DocumentSnapshot
from basho.connectors.http import ConnectorErrorKind, JsonApi
from basho.resilience import RetryPolicy

CONNECTOR = "notion"
DEFAULT_API_URL = "https://api.notion.com"
NOTION_VERSION = "2022-06-28"
PAGE_SIZE = 100
MAX_PAGES = 200
MAX_BLOCKS = 500
_ID = re.compile(
    r"^[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12}$"
)


@dataclass(frozen=True, slots=True)
class NotionRef:
    """Database ou página do Notion. `kind` é `database` ou `page`; o ID é validado."""

    kind: str
    object_id: str

    def __post_init__(self) -> None:
        if self.kind not in ("database", "page") or not _ID.fullmatch(self.object_id):
            msg = "referência do Notion deve ser database:<id> ou page:<id>"
            raise ValueError(msg)

    @classmethod
    def parse(cls, value: str) -> NotionRef:
        kind, _, object_id = value.partition(":")
        return cls(kind.strip(), object_id.strip().replace("-", ""))

    @property
    def scope(self) -> str:
        return f"{self.kind}:{self.object_id}"


class NotionClient:
    def __init__(
        self,
        *,
        token: SecretStr,
        http_client: httpx.AsyncClient,
        api_url: str = DEFAULT_API_URL,
        retry: RetryPolicy | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._token = token

        async def auth() -> dict[str, str]:
            return {"Authorization": f"Bearer {self._token.get_secret_value()}"}

        self._api = JsonApi(
            CONNECTOR,
            api_url=api_url,
            http_client=http_client,
            auth_headers=auth,
            extra_headers={"Notion-Version": NOTION_VERSION},
            retry=retry,
            sleep=sleep,
        )

    async def query_database(
        self, database_id: str, *, since: datetime | None = None, limit: int = MAX_PAGES
    ) -> list[dict[str, Any]]:
        url = f"{self._api.api_url}/v1/databases/{database_id}/query"
        body: dict[str, Any] = {
            "page_size": PAGE_SIZE,
            "sorts": [{"timestamp": "last_edited_time", "direction": "descending"}],
        }
        if since is not None:
            body["filter"] = {
                "timestamp": "last_edited_time",
                "last_edited_time": {"on_or_after": since.isoformat()},
            }
        bounded = max(1, min(limit, MAX_PAGES))
        pages: list[dict[str, Any]] = []
        while len(pages) < bounded:
            data = await self._api.json("POST", url, json=body)
            pages.extend(_results(data, self._api))
            cursor = _next_cursor(data)
            if cursor is None:
                break
            body = {**body, "start_cursor": cursor}
        return pages[:bounded]

    async def get_page(self, page_id: str) -> dict[str, Any]:
        return await self._api.json("GET", f"{self._api.api_url}/v1/pages/{page_id}")

    async def page_text(self, page_id: str) -> str:
        url = f"{self._api.api_url}/v1/blocks/{page_id}/children"
        params: dict[str, Any] = {"page_size": PAGE_SIZE}
        lines: list[str] = []
        seen = 0
        while seen < MAX_BLOCKS:
            data = await self._api.json("GET", url, params=params)
            blocks = _results(data, self._api)
            seen += len(blocks)
            lines.extend(line for line in map(_block_text, blocks) if line)
            cursor = _next_cursor(data)
            if cursor is None:
                break
            params = {**params, "start_cursor": cursor}
        return "\n".join(lines)

    async def snapshots(
        self, ref: NotionRef, *, since: datetime | None = None
    ) -> list[DocumentSnapshot]:
        if ref.kind == "database":
            pages = await self.query_database(ref.object_id, since=since)
        else:
            pages = [await self.get_page(ref.object_id)]
        result = []
        for page in pages:
            snapshot = await self._snapshot(page)
            if snapshot is not None:
                result.append(snapshot)
        return result

    async def _snapshot(self, page: dict[str, Any]) -> DocumentSnapshot | None:
        page_id, edited = page.get("id"), _timestamp(page.get("last_edited_time"))
        if not isinstance(page_id, str) or not _ID.fullmatch(page_id) or edited is None:
            return None
        if page.get("archived") is True or page.get("in_trash") is True:
            return None
        doc_id = page_id.replace("-", "")
        url = page.get("url")
        return DocumentSnapshot(
            doc_id=doc_id,
            revision=edited,
            title=_title(page),
            url=url if isinstance(url, str) and url.startswith("https://") else None,
            mime_type="notion/page",
            modified_at=edited,
            text=_with_properties(page, await self.page_text(doc_id)),
        )


def _results(data: dict[str, Any], api: JsonApi) -> list[dict[str, Any]]:
    items = data.get("results")
    if not isinstance(items, list):
        raise api.error(ConnectorErrorKind.INVALID_RESPONSE)
    return [item for item in items if isinstance(item, dict)]


def _next_cursor(data: dict[str, Any]) -> str | None:
    cursor = data.get("next_cursor")
    if data.get("has_more") is True and isinstance(cursor, str) and cursor:
        return cursor
    return None


def _plain(rich: object) -> str:
    if not isinstance(rich, list):
        return ""
    return "".join(
        str(part["plain_text"])
        for part in rich
        if isinstance(part, dict) and isinstance(part.get("plain_text"), str)
    )


def _block_text(block: dict[str, Any]) -> str:
    kind = block.get("type")
    content = block.get(kind) if isinstance(kind, str) else None
    if not isinstance(content, dict):
        return ""
    text = _plain(content.get("rich_text"))
    if kind == "to_do" and text:
        return f"[{'x' if content.get('checked') is True else ' '}] {text}"
    if kind in ("heading_1", "heading_2", "heading_3") and text:
        return f"{'#' * int(str(kind)[-1])} {text}"
    if kind == "bulleted_list_item" and text:
        return f"- {text}"
    return text


def _property_value(value: dict[str, Any]) -> str | None:
    """Só tipos estruturados: status, seleção, data, caixa e número.

    `people`, `rich_text`, e-mail e afins ficam de fora (LGPD, ADR-0006; e alocação de pessoas
    só vem de registro formal, regra 6 do CLAUDE.md).
    """
    kind = value.get("type")
    content = value.get(kind) if isinstance(kind, str) else None
    if kind in ("select", "status") and isinstance(content, dict):
        name = content.get("name")
        return name if isinstance(name, str) else None
    if kind == "multi_select" and isinstance(content, list):
        names = [
            o["name"] for o in content if isinstance(o, dict) and isinstance(o.get("name"), str)
        ]
        return ", ".join(names) or None
    if kind == "date" and isinstance(content, dict):
        start, end = content.get("start"), content.get("end")
        if not isinstance(start, str):
            return None
        return f"{start} → {end}" if isinstance(end, str) else start
    if kind == "checkbox" and isinstance(content, bool):
        return "sim" if content else "não"
    if kind == "number" and isinstance(content, int | float) and not isinstance(content, bool):
        return str(content)
    return None


def _with_properties(page: dict[str, Any], body: str) -> str:
    properties = page.get("properties")
    lines = []
    if isinstance(properties, dict):
        for name, value in sorted(properties.items()):
            if isinstance(value, dict) and (rendered := _property_value(value)) is not None:
                lines.append(f"{name}: {rendered}")
    if not lines:
        return body
    header = "Propriedades:\n" + "\n".join(f"- {line}" for line in lines)
    return f"{header}\n\n{body}" if body else header


def _title(page: dict[str, Any]) -> str:
    properties = page.get("properties")
    if isinstance(properties, dict):
        for value in properties.values():
            if isinstance(value, dict) and value.get("type") == "title":
                return _plain(value.get("title"))
    return ""


def _timestamp(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return None
