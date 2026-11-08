"""Cliente mínimo da API do Google Drive v3, só leitura (ADR-0012).

Auth: OAuth 2.0 com refresh token (`GOOGLE_DRIVE_CLIENT_ID`, `..._CLIENT_SECRET`,
`..._REFRESH_TOKEN`), escopo `drive.readonly`. O access token é renovado sob demanda, fica só em
memória e nunca aparece em erro ou log.

Lê os arquivos de uma pasta (sem descer em subpastas no MVP). Docs/Sheets/Slides são
exportados como texto; arquivos de texto são baixados até `MAX_DOWNLOAD_BYTES`; o resto (PDF,
imagem) entra só com metadados e o `md5Checksum` do Drive.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
from pydantic import SecretStr

from basho.connectors.documents import DocumentSnapshot
from basho.connectors.http import ConnectorError, ConnectorErrorKind, JsonApi
from basho.resilience import RetryPolicy

CONNECTOR = "google_drive"
DEFAULT_API_URL = "https://www.googleapis.com"
DEFAULT_TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105 - URL, não segredo
PAGE_SIZE = 100
MAX_FILES = 300
MAX_DOWNLOAD_BYTES = 1_000_000
_TOKEN_MARGIN_SECONDS = 60.0
_FOLDER_MIME = "application/vnd.google-apps.folder"
_EXPORTS = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
    "application/vnd.google-apps.presentation": "text/plain",
}
_TEXT_MIMES = frozenset({"application/json", "text/markdown", "text/csv", "text/plain"})
_FIELDS = "nextPageToken,files(id,name,mimeType,modifiedTime,version,md5Checksum,size,webViewLink)"
_ID = re.compile(r"^[A-Za-z0-9_-]{10,200}$")


@dataclass(frozen=True, slots=True)
class FolderRef:
    """ID de pasta do Drive validado: entra na query `q`, então não aceita aspas nem espaço."""

    folder_id: str

    def __post_init__(self) -> None:
        if not _ID.fullmatch(self.folder_id):
            msg = "ID de pasta do Drive inválido"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class DriveCredentials:
    client_id: str
    client_secret: SecretStr
    refresh_token: SecretStr


class GoogleDriveClient:
    def __init__(
        self,
        *,
        credentials: DriveCredentials,
        http_client: httpx.AsyncClient,
        api_url: str = DEFAULT_API_URL,
        token_url: str = DEFAULT_TOKEN_URL,
        retry: RetryPolicy | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._credentials = credentials
        self._http = http_client
        self._token_url = token_url
        self._clock = clock
        self._access_token: str | None = None
        self._expires_at = 0.0
        self._token_lock = asyncio.Lock()
        self._api = JsonApi(
            CONNECTOR,
            api_url=api_url,
            http_client=http_client,
            auth_headers=self._auth_headers,
            retry=retry,
            sleep=sleep,
        )

    async def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {await self._token()}"}

    async def _token(self) -> str:
        async with self._token_lock:
            if self._access_token is not None and self._clock() < self._expires_at:
                return self._access_token
            try:
                response = await self._http.post(
                    self._token_url,
                    data={
                        "grant_type": "refresh_token",
                        "client_id": self._credentials.client_id,
                        "client_secret": self._credentials.client_secret.get_secret_value(),
                        "refresh_token": self._credentials.refresh_token.get_secret_value(),
                    },
                    timeout=20.0,
                )
            except httpx.HTTPError:
                raise ConnectorError(CONNECTOR, ConnectorErrorKind.NETWORK) from None
            if response.status_code in (400, 401, 403):
                # invalid_grant/invalid_client: refresh token revogado ou credencial errada
                raise ConnectorError(CONNECTOR, ConnectorErrorKind.UNAUTHORIZED, 401)
            if response.status_code >= 400:
                raise ConnectorError(CONNECTOR, ConnectorErrorKind.HTTP_ERROR, response.status_code)
            try:
                data = response.json()
                token = data["access_token"]
                expires_in = float(data.get("expires_in", 3600))
            except (ValueError, KeyError, TypeError):
                raise ConnectorError(CONNECTOR, ConnectorErrorKind.INVALID_RESPONSE) from None
            if not isinstance(token, str) or not token:
                raise ConnectorError(CONNECTOR, ConnectorErrorKind.INVALID_RESPONSE)
            self._access_token = token
            self._expires_at = self._clock() + max(expires_in - _TOKEN_MARGIN_SECONDS, 0.0)
            return token

    async def list_files(
        self, folder: FolderRef, *, since: datetime | None = None, limit: int = MAX_FILES
    ) -> list[dict[str, Any]]:
        query = f"'{folder.folder_id}' in parents and trashed = false"
        if since is not None:
            query += f" and modifiedTime > '{since.isoformat()}'"
        url = f"{self._api.api_url}/drive/v3/files"
        params: dict[str, Any] = {
            "q": query,
            "fields": _FIELDS,
            "pageSize": PAGE_SIZE,
            "orderBy": "modifiedTime desc",
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        }
        bounded = max(1, min(limit, MAX_FILES))
        files: list[dict[str, Any]] = []
        while len(files) < bounded:
            page = await self._api.json("GET", url, params=params)
            items = page.get("files")
            if not isinstance(items, list):
                raise self._api.error(ConnectorErrorKind.INVALID_RESPONSE)
            files.extend(item for item in items if isinstance(item, dict))
            token = page.get("nextPageToken")
            if not isinstance(token, str) or not token:
                break
            params = {**params, "pageToken": token}
        return files[:bounded]

    async def read_text(self, item: dict[str, Any]) -> str | None:
        """Texto do arquivo, ou `None` se o formato não é lido como texto ou é grande demais."""
        file_id, mime = item.get("id"), item.get("mimeType")
        if not isinstance(file_id, str) or not _ID.fullmatch(file_id) or not isinstance(mime, str):
            return None
        base = f"{self._api.api_url}/drive/v3/files/{file_id}"
        if mime in _EXPORTS:
            response = await self._api.request(
                "GET", f"{base}/export", params={"mimeType": _EXPORTS[mime]}
            )
        elif mime.startswith("text/") or mime in _TEXT_MIMES:
            size = _int(item.get("size"))
            if size is None or size > MAX_DOWNLOAD_BYTES:
                return None
            response = await self._api.request(
                "GET", base, params={"alt": "media", "supportsAllDrives": "true"}
            )
        else:
            return None
        return response.content[:MAX_DOWNLOAD_BYTES].decode("utf-8", errors="replace")

    async def snapshots(
        self, folder: FolderRef, *, since: datetime | None = None
    ) -> list[DocumentSnapshot]:
        result = []
        for item in await self.list_files(folder, since=since):
            snapshot = await self._snapshot(item)
            if snapshot is not None:
                result.append(snapshot)
        return result

    async def _snapshot(self, item: dict[str, Any]) -> DocumentSnapshot | None:
        file_id, mime = item.get("id"), item.get("mimeType")
        if not isinstance(file_id, str) or not _ID.fullmatch(file_id) or mime == _FOLDER_MIME:
            return None
        modified = _timestamp(item.get("modifiedTime"))
        revision = item.get("version")
        if not isinstance(revision, str) or not revision.isdigit():
            revision = modified or "unknown"
        link = item.get("webViewLink")
        checksum = item.get("md5Checksum")
        return DocumentSnapshot(
            doc_id=file_id,
            revision=revision,
            title=name if isinstance(name := item.get("name"), str) else "",
            url=link if isinstance(link, str) and link.startswith("https://") else None,
            mime_type=mime if isinstance(mime, str) else None,
            modified_at=modified,
            text=await self.read_text(item),
            checksum=checksum if isinstance(checksum, str) else None,
        )


def _int(value: object) -> int | None:
    try:
        return int(str(value))
    except ValueError:
        return None


def _timestamp(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return None
