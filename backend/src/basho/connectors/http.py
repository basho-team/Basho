"""Base HTTP dos conectores de documentos (Drive, Notion; ADR-0010).

Mesmas garantias do cliente GitHub (#7/#25): só leitura, retry de falha transitória com
`call_with_retry`, erro com código estável e **sem** segredo na mensagem, e `retryable` para o
worker decidir se reagenda o run.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from enum import StrEnum
from typing import Any

import httpx

from basho.logging import get_logger
from basho.resilience import RetryPolicy, call_with_retry

DEFAULT_TIMEOUT_SECONDS = 20.0
USER_AGENT = "basho-connector"
_SERVER_ERROR_FLOOR = 500

_log = get_logger(__name__)


class ConnectorErrorKind(StrEnum):
    UNAUTHORIZED = "unauthorized"
    NOT_FOUND = "not_found"
    RATE_LIMITED = "rate_limited"
    HTTP_ERROR = "http_error"
    NETWORK = "network"
    INVALID_RESPONSE = "invalid_response"


class ConnectorError(RuntimeError):
    """Falha de um conector. `code` é `<conector>_<tipo>` (ex.: `notion_rate_limited`)."""

    def __init__(
        self,
        connector: str,
        kind: ConnectorErrorKind,
        status: int | None = None,
        *,
        retry_after: float | None = None,
    ) -> None:
        self.connector = connector
        self.kind = kind
        self.code = f"{connector}_{kind.value}"
        self.status = status
        self.retry_after = retry_after
        super().__init__(self.code if status is None else f"{self.code} (HTTP {status})")

    @property
    def retryable(self) -> bool:
        if self.kind in (ConnectorErrorKind.RATE_LIMITED, ConnectorErrorKind.NETWORK):
            return True
        return (
            self.kind is ConnectorErrorKind.HTTP_ERROR
            and self.status is not None
            and self.status >= _SERVER_ERROR_FLOOR
        )


AuthHeaders = Callable[[], Awaitable[Mapping[str, str]]]


class JsonApi:
    """Requisições a uma API JSON com auth injetada, retry e checagem de host.

    `auth_headers` é chamado a cada tentativa (o Drive renova o access token aí). O host da
    URL precisa começar por `api_url`: o token nunca segue para outro destino.
    """

    def __init__(
        self,
        connector: str,
        *,
        api_url: str,
        http_client: httpx.AsyncClient,
        auth_headers: AuthHeaders,
        extra_headers: Mapping[str, str] | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        retry: RetryPolicy | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.connector = connector
        self.api_url = api_url.rstrip("/")
        self._http = http_client
        self._auth_headers = auth_headers
        self._extra = dict(extra_headers or {})
        self._timeout = timeout
        self._retry = retry or RetryPolicy()
        self._sleep = sleep

    def error(self, kind: ConnectorErrorKind, status: int | None = None) -> ConnectorError:
        return ConnectorError(self.connector, kind, status)

    async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        if not url.startswith(self.api_url + "/"):
            raise self.error(ConnectorErrorKind.INVALID_RESPONSE)

        async def attempt() -> httpx.Response:
            headers = {"User-Agent": USER_AGENT, **self._extra, **(await self._auth_headers())}
            try:
                response = await self._http.request(
                    method, url, headers=headers, timeout=self._timeout, **kwargs
                )
            except httpx.HTTPError:
                raise self.error(ConnectorErrorKind.NETWORK) from None
            self._raise_for_status(response)
            return response

        def log_retry(number: int, exc: Exception, delay: float) -> None:
            code = exc.code if isinstance(exc, ConnectorError) else type(exc).__name__
            _log.warning(
                "connector_retry", attempt=number, code=code, delay_seconds=round(delay, 2)
            )

        return await call_with_retry(
            attempt,
            policy=self._retry,
            is_retryable=lambda exc: isinstance(exc, ConnectorError) and exc.retryable,
            retry_after=lambda exc: exc.retry_after if isinstance(exc, ConnectorError) else None,
            on_retry=log_retry,
            sleep=self._sleep,
        )

    async def json(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        response = await self.request(method, url, **kwargs)
        try:
            data = response.json()
        except ValueError:
            raise self.error(ConnectorErrorKind.INVALID_RESPONSE) from None
        if not isinstance(data, dict):
            raise self.error(ConnectorErrorKind.INVALID_RESPONSE)
        return data

    def _raise_for_status(self, response: httpx.Response) -> None:
        status = response.status_code
        if status < 400:
            return
        if status == 429:
            raise ConnectorError(
                self.connector,
                ConnectorErrorKind.RATE_LIMITED,
                status,
                retry_after=_retry_after(response.headers),
            )
        if status in (401, 403):
            raise self.error(ConnectorErrorKind.UNAUTHORIZED, status)
        if status == 404:
            raise self.error(ConnectorErrorKind.NOT_FOUND, status)
        raise self.error(ConnectorErrorKind.HTTP_ERROR, status)


def _retry_after(headers: httpx.Headers) -> float | None:
    raw = headers.get("retry-after")
    if raw is None:
        return None
    try:
        return max(float(raw), 0.0)
    except ValueError:
        return None
