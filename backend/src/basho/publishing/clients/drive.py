"""Cliente mínimo da API do Google Drive v3 (httpx, sem SDK).

Só o necessário para o Basho: validar a pasta que o usuário compartilhou, garantir a subpasta
``BASHO`` e criar o relatório como Google Doc (HTML convertido). Antes de criar, procura por nome:
reexecutar depois de falha não duplica (verificar o efeito externo antes de repetir). Leituras
repetem falha transitória; escrita não é repetida às cegas.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import httpx

from basho.publishing.clients.errors import ProviderError, ProviderErrorCode, error_from_status
from basho.publishing.clients.google_auth import TokenSource
from basho.resilience import RetryPolicy, call_with_retry

API_URL = "https://www.googleapis.com"
FOLDER_MIME = "application/vnd.google-apps.folder"
DOC_MIME = "application/vnd.google-apps.document"
BASHO_FOLDER_NAME = "BASHO"
DEFAULT_TIMEOUT_SECONDS = 20.0
_ID = re.compile(r"[A-Za-z0-9_-]{10,128}")
_COMMON = {"supportsAllDrives": "true"}


@dataclass(frozen=True, slots=True)
class DriveFolder:
    id: str
    name: str
    can_add_children: bool


@dataclass(frozen=True, slots=True)
class DriveFile:
    id: str
    name: str
    url: str


def _query_literal(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _require_id(value: str) -> str:
    if not _ID.fullmatch(value):
        raise ProviderError(ProviderErrorCode.BAD_REQUEST)
    return value


def _is_retryable(exc: Exception) -> bool:
    return isinstance(exc, ProviderError) and exc.retryable


class DriveClient:
    def __init__(
        self,
        *,
        tokens: TokenSource,
        http: httpx.AsyncClient,
        api_url: str = API_URL,
        retry: RetryPolicy | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._tokens = tokens
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
        content: bytes | None = None,
        json_body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        repeatable: bool,
    ) -> dict[str, Any]:
        async def once() -> dict[str, Any]:
            token = await self._tokens.token()
            try:
                response = await self._http.request(
                    method,
                    f"{self._api_url}{path}",
                    params=params,
                    content=content,
                    json=json_body,
                    headers={"Authorization": f"Bearer {token}", **(headers or {})},
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

    async def get_folder(self, folder_id: str) -> DriveFolder:
        """Valida que a pasta existe, é pasta e aceita novos itens para a conta do Basho."""
        body = await self._send(
            "GET",
            f"/drive/v3/files/{_require_id(folder_id)}",
            params={**_COMMON, "fields": "id,name,mimeType,capabilities(canAddChildren)"},
            repeatable=True,
        )
        if body.get("mimeType") != FOLDER_MIME:
            raise ProviderError(ProviderErrorCode.NOT_A_FOLDER)
        capabilities = body.get("capabilities")
        can_add = (
            bool(capabilities.get("canAddChildren")) if isinstance(capabilities, dict) else False
        )
        return DriveFolder(
            id=str(body["id"]), name=str(body.get("name", "")), can_add_children=can_add
        )

    async def _find_child(self, parent_id: str, name: str, *, folder: bool) -> DriveFile | None:
        mime_filter = (
            "mimeType = 'application/vnd.google-apps.folder'"
            if folder
            else ("mimeType != 'application/vnd.google-apps.folder'")
        )
        query = (
            f"'{_require_id(parent_id)}' in parents and name = '{_query_literal(name)}' "
            f"and {mime_filter} and trashed = false"
        )
        body = await self._send(
            "GET",
            "/drive/v3/files",
            params={
                **_COMMON,
                "includeItemsFromAllDrives": "true",
                "q": query,
                "pageSize": "1",
                "fields": "files(id,name,webViewLink)",
            },
            repeatable=True,
        )
        files = body.get("files")
        if not isinstance(files, list) or not files:
            return None
        first = files[0]
        return DriveFile(
            id=str(first["id"]),
            name=str(first.get("name", name)),
            url=str(first.get("webViewLink", "")),
        )

    async def ensure_folder(self, parent_id: str, name: str = BASHO_FOLDER_NAME) -> str:
        existing = await self._find_child(parent_id, name, folder=True)
        if existing is not None:
            return existing.id
        body = await self._send(
            "POST",
            "/drive/v3/files",
            params={**_COMMON, "fields": "id"},
            json_body={"name": name, "mimeType": FOLDER_MIME, "parents": [_require_id(parent_id)]},
            repeatable=False,
        )
        return str(body["id"])

    async def create_document(self, parent_id: str, name: str, html: str) -> DriveFile:
        """Cria um Google Doc a partir de HTML; se já existir um arquivo com o nome, reutiliza."""
        existing = await self._find_child(parent_id, name, folder=False)
        if existing is not None:
            return existing
        boundary = f"basho{uuid4().hex}"
        metadata = json.dumps(
            {"name": name, "mimeType": DOC_MIME, "parents": [_require_id(parent_id)]}
        )
        payload = (
            f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{metadata}\r\n"
            f"--{boundary}\r\nContent-Type: text/html; charset=UTF-8\r\n\r\n{html}\r\n"
            f"--{boundary}--"
        ).encode()
        body = await self._send(
            "POST",
            "/upload/drive/v3/files",
            params={**_COMMON, "uploadType": "multipart", "fields": "id,name,webViewLink"},
            content=payload,
            headers={"Content-Type": f"multipart/related; boundary={boundary}"},
            repeatable=False,
        )
        return DriveFile(
            id=str(body["id"]),
            name=str(body.get("name", name)),
            url=str(body.get("webViewLink", "")),
        )
