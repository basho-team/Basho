"""Cliente mínimo da API REST do GitHub (httpx), com paginação e rate limit.

O token vem só de `Settings.github_token` (variável de ambiente) e nunca aparece em erro ou
log. Erros viram `GithubError(code)` com código estável; `retryable` diz ao worker se cabe
nova tentativa (#25).
"""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

import httpx
from pydantic import SecretStr

from basho.logging import get_logger
from basho.resilience import RetryPolicy, call_with_retry

DEFAULT_API_URL = "https://api.github.com"
DEFAULT_TIMEOUT_SECONDS = 20.0
PAGE_SIZE = 100
MAX_ITEMS = 500
API_VERSION = "2022-11-28"
USER_AGENT = "basho-connector"
WRITE_INTERVAL_SECONDS = 1.0
"""Escritas espaçadas em ≥ 1s e em série (guia de boas práticas da API do GitHub)."""
ISSUE_LOOKUP_LIMIT = 200
"""Quantas issues recentes a verificação de efeito examina antes de reenviar um POST."""
IDEMPOTENCY_MARKER = "<!-- basho-idempotency-key:{key} -->"
_KEY = re.compile(r"^[A-Za-z0-9_-]{8,128}$")

_log = get_logger(__name__)

_REPO = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9._-]{1,100}$")
_NEXT_LINK = re.compile(r'<([^>]+)>;\s*rel="next"')


class GithubErrorCode(StrEnum):
    UNAUTHORIZED = "github_unauthorized"
    NOT_FOUND = "github_not_found"
    RATE_LIMITED = "github_rate_limited"
    HTTP_ERROR = "github_http_error"
    NETWORK = "github_network"
    INVALID_RESPONSE = "github_invalid_response"


_SERVER_ERROR_FLOOR = 500


class GithubError(RuntimeError):
    """Falha do GitHub com código estável e sem segredo na mensagem.

    `retryable` é só para falha transitória: rate limit, rede e 5xx. Outros 4xx (422, 409...)
    não melhoram com nova tentativa. `retry_after` é a espera pedida pelo GitHub, em segundos;
    `attempts` é quantas tentativas foram feitas antes de desistir.
    """

    def __init__(
        self,
        code: GithubErrorCode,
        status: int | None = None,
        *,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(code.value if status is None else f"{code.value} (HTTP {status})")
        self.code = code
        self.status = status
        self.retry_after = retry_after
        self.attempts = 1

    @property
    def retryable(self) -> bool:
        if self.code in (GithubErrorCode.RATE_LIMITED, GithubErrorCode.NETWORK):
            return True
        return (
            self.code is GithubErrorCode.HTTP_ERROR
            and self.status is not None
            and self.status >= _SERVER_ERROR_FLOOR
        )


@dataclass(frozen=True)
class IssueResult:
    """Issue garantida no destino: `reused` é True quando já existia e nada foi criado."""

    number: int
    reused: bool


@dataclass(frozen=True)
class RepoRef:
    """`owner/name` validado: nunca vira caminho arbitrário na URL."""

    full_name: str

    def __post_init__(self) -> None:
        name = self.full_name.split("/")[-1]
        if not _REPO.fullmatch(self.full_name) or set(name) == {"."}:
            msg = "repositório deve ser owner/name"
            raise ValueError(msg)


class GithubClient:
    def __init__(
        self,
        *,
        token: SecretStr,
        http_client: httpx.AsyncClient,
        api_url: str = DEFAULT_API_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        retry: RetryPolicy | None = None,
        write_interval: float = WRITE_INTERVAL_SECONDS,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._token = token
        self._http = http_client
        self._api_url = api_url.rstrip("/")
        self._timeout = timeout
        self._retry = retry or RetryPolicy()
        self._write_interval = write_interval
        self._sleep = sleep
        self._clock = clock
        self._last_write: float | None = None
        self._write_lock = asyncio.Lock()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token.get_secret_value()}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": USER_AGENT,
        }

    async def _send(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Uma tentativa, sem retry."""
        try:
            response = await self._http.request(
                method, url, headers=self._headers(), timeout=self._timeout, **kwargs
            )
        except httpx.HTTPError:
            raise GithubError(GithubErrorCode.NETWORK) from None
        _raise_for_status(response)
        return response

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Leitura (GET) com retry de falha transitória; sem efeito externo, logo repetível.

        Rate limit espera o que o GitHub pediu (`Retry-After`/`x-ratelimit-reset`); se o pedido
        passar de `max_delay`, desiste na hora e deixa o worker reagendar usando `retry_after`.
        """
        attempts = 0

        async def attempt() -> httpx.Response:
            nonlocal attempts
            attempts += 1
            return await self._send(method, url, **kwargs)

        def log_retry(number: int, exc: Exception, delay: float) -> None:
            code = exc.code.value if isinstance(exc, GithubError) else type(exc).__name__
            _log.warning("github_retry", attempt=number, code=code, delay_seconds=round(delay, 2))

        try:
            return await call_with_retry(
                attempt,
                policy=self._retry,
                is_retryable=_is_retryable,
                retry_after=_retry_after,
                on_retry=log_retry,
                sleep=self._sleep,
            )
        except GithubError as exc:
            exc.attempts = attempts
            raise

    async def _write(self, url: str, payload: dict[str, Any]) -> httpx.Response:
        """POST sem retry próprio, em série e espaçado: repetir escrita exige verificar antes."""
        async with self._write_lock:
            if self._last_write is not None:
                wait = self._write_interval - (self._clock() - self._last_write)
                if wait > 0:
                    await self._sleep(wait)
            try:
                return await self._send("POST", url, json=payload)
            finally:
                self._last_write = self._clock()

    async def _paginate(
        self, path: str, params: dict[str, Any], limit: int
    ) -> list[dict[str, Any]]:
        bounded = max(1, min(limit, MAX_ITEMS))
        url: str | None = f"{self._api_url}{path}"
        query: dict[str, Any] | None = {**params, "per_page": PAGE_SIZE}
        items: list[dict[str, Any]] = []
        while url is not None and len(items) < bounded:
            response = await self._request("GET", url, params=query)
            page = _json(response)
            if not isinstance(page, list):
                raise GithubError(GithubErrorCode.INVALID_RESPONSE)
            items.extend(item for item in page if isinstance(item, dict))
            url = _next_link(response)
            if url is not None and not url.startswith(self._api_url + "/"):
                # Defesa em profundidade: o token só segue para o próprio host da API.
                raise GithubError(GithubErrorCode.INVALID_RESPONSE)
            query = None  # o link `next` já carrega os parâmetros
        return items[:bounded]

    async def list_commits(
        self, repo: RepoRef, *, since: datetime | None = None, limit: int = PAGE_SIZE
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        if since is not None:
            params["since"] = since.isoformat()
        return await self._paginate(f"/repos/{repo.full_name}/commits", params, limit)

    async def list_pull_requests(
        self, repo: RepoRef, *, limit: int = PAGE_SIZE
    ) -> list[dict[str, Any]]:
        params = {"state": "all", "sort": "updated", "direction": "desc"}
        return await self._paginate(f"/repos/{repo.full_name}/pulls", params, limit)

    async def get_pull_request(self, repo: RepoRef, number: int) -> dict[str, Any]:
        url = f"{self._api_url}/repos/{repo.full_name}/pulls/{int(number)}"
        data = _json(await self._request("GET", url))
        if not isinstance(data, dict):
            raise GithubError(GithubErrorCode.INVALID_RESPONSE)
        return data

    async def create_issue(self, repo: RepoRef, *, title: str, body: str) -> dict[str, Any]:
        """Uma única tentativa, sem retry nem deduplicação. Prefira `ensure_issue`."""
        url = f"{self._api_url}/repos/{repo.full_name}/issues"
        data = _json(await self._write(url, {"title": title, "body": body}))
        if not isinstance(data, dict):
            raise GithubError(GithubErrorCode.INVALID_RESPONSE)
        return data

    async def find_issue_by_key(self, repo: RepoRef, key: str) -> int | None:
        """Número da issue (não PR) criada com esta chave de idempotência, ou `None`.

        Examina as `ISSUE_LOOKUP_LIMIT` issues mais recentes, abertas e fechadas. A listagem de
        issues é consistente (não é o índice de busca, que atrasa), então serve de verificação.
        """
        marker = IDEMPOTENCY_MARKER.format(key=_valid_key(key))
        issues = await self._paginate(
            f"/repos/{repo.full_name}/issues",
            {"state": "all", "sort": "created", "direction": "desc"},
            ISSUE_LOOKUP_LIMIT,
        )
        for item in issues:
            number, body = item.get("number"), item.get("body")
            if (
                "pull_request" not in item  # a listagem de issues também devolve PRs
                and isinstance(body, str)
                and marker in body
                and isinstance(number, int)
                and not isinstance(number, bool)
            ):
                return number
        return None

    async def ensure_issue(
        self, repo: RepoRef, *, title: str, body: str, idempotency_key: str
    ) -> IssueResult:
        """Garante **uma** issue por `idempotency_key`, mesmo com timeout, 5xx e replays.

        1. Consulta o destino: se a chave já foi usada, devolve a issue existente (`reused`).
        2. Cria com a chave num marcador no corpo.
        3. Se o POST falhar de forma transitória, o efeito é desconhecido (o GitHub pode ter
           criado e a resposta se perdido): **consulta o destino antes de reenviar**. Se a
           consulta também falhar, sobe o erro; nunca reenvia sem ter verificado.

        Falha permanente (401/404/422...) sobe na hora. Ao esgotar as tentativas, sobe o último
        erro com `attempts` preenchido, para o chamador registrar o contexto.
        """
        marker = IDEMPOTENCY_MARKER.format(key=_valid_key(idempotency_key))
        attempt = 1
        try:
            existing = await self.find_issue_by_key(repo, idempotency_key)
            if existing is not None:
                return IssueResult(number=existing, reused=True)
            url = f"{self._api_url}/repos/{repo.full_name}/issues"
            payload = {"title": title, "body": f"{body}\n\n{marker}"}
            while True:
                try:
                    data = _json(await self._write(url, payload))
                except GithubError as exc:
                    delay = (
                        self._retry.next_delay(attempt, exc.retry_after)
                        if exc.retryable and attempt < self._retry.max_attempts
                        else None
                    )
                    if delay is None:
                        raise
                    _log.warning(
                        "github_issue_retry",
                        attempt=attempt,
                        code=exc.code.value,
                        delay_seconds=round(delay, 2),
                    )
                    await self._sleep(delay)
                    found = await self.find_issue_by_key(repo, idempotency_key)
                    if found is not None:
                        return IssueResult(number=found, reused=True)
                    attempt += 1
                    continue
                number = data.get("number") if isinstance(data, dict) else None
                if not isinstance(number, int) or isinstance(number, bool):
                    raise GithubError(GithubErrorCode.INVALID_RESPONSE)
                return IssueResult(number=number, reused=False)
        except GithubError as exc:
            exc.attempts = max(exc.attempts, attempt)
            raise


def _json(response: httpx.Response) -> object:
    try:
        return response.json()
    except ValueError:
        raise GithubError(GithubErrorCode.INVALID_RESPONSE) from None


def _next_link(response: httpx.Response) -> str | None:
    match = _NEXT_LINK.search(response.headers.get("link", ""))
    return match.group(1) if match else None


def _valid_key(key: str) -> str:
    if not _KEY.fullmatch(key):
        msg = "idempotency_key deve ter 8 a 128 caracteres [A-Za-z0-9_-]"
        raise ValueError(msg)
    return key


def _is_retryable(exc: Exception) -> bool:
    return isinstance(exc, GithubError) and exc.retryable


def _retry_after(exc: Exception) -> float | None:
    return exc.retry_after if isinstance(exc, GithubError) else None


def _wait_requested(headers: httpx.Headers) -> float | None:
    """Espera pedida pelo GitHub: `Retry-After` (segundos) ou `x-ratelimit-reset` (epoch)."""
    for name, relative in (("retry-after", True), ("x-ratelimit-reset", False)):
        raw = headers.get(name)
        if raw is None:
            continue
        try:
            value = float(raw)
        except ValueError:
            continue
        return max(value if relative else value - time.time(), 0.0)
    return None


def _raise_for_status(response: httpx.Response) -> None:
    status = response.status_code
    if status < 400:
        return
    if status == 429 or (status == 403 and response.headers.get("x-ratelimit-remaining") == "0"):
        raise GithubError(
            GithubErrorCode.RATE_LIMITED, status, retry_after=_wait_requested(response.headers)
        )
    if status in (401, 403):
        raise GithubError(GithubErrorCode.UNAUTHORIZED, status)
    if status == 404:
        raise GithubError(GithubErrorCode.NOT_FOUND, status)
    raise GithubError(GithubErrorCode.HTTP_ERROR, status)
