"""Cliente mínimo da API REST do GitHub (httpx), com paginação e rate limit.

O token vem só de `Settings.github_token` (variável de ambiente) e nunca aparece em erro ou
log. Erros viram `GithubError(code)` com código estável; `retryable` diz ao worker se cabe
nova tentativa (#25).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

import httpx
from pydantic import SecretStr

DEFAULT_API_URL = "https://api.github.com"
DEFAULT_TIMEOUT_SECONDS = 20.0
PAGE_SIZE = 100
MAX_ITEMS = 500
API_VERSION = "2022-11-28"
USER_AGENT = "basho-connector"

_REPO = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9._-]{1,100}$")
_NEXT_LINK = re.compile(r'<([^>]+)>;\s*rel="next"')


class GithubErrorCode(StrEnum):
    UNAUTHORIZED = "github_unauthorized"
    NOT_FOUND = "github_not_found"
    RATE_LIMITED = "github_rate_limited"
    HTTP_ERROR = "github_http_error"
    NETWORK = "github_network"
    INVALID_RESPONSE = "github_invalid_response"


_RETRYABLE = frozenset(
    {GithubErrorCode.RATE_LIMITED, GithubErrorCode.NETWORK, GithubErrorCode.HTTP_ERROR}
)


class GithubError(RuntimeError):
    """Falha do GitHub com código estável e sem segredo na mensagem."""

    def __init__(self, code: GithubErrorCode, status: int | None = None) -> None:
        super().__init__(code.value if status is None else f"{code.value} (HTTP {status})")
        self.code = code
        self.status = status

    @property
    def retryable(self) -> bool:
        return self.code in _RETRYABLE


@dataclass(frozen=True)
class RepoRef:
    """`owner/name` validado: nunca vira caminho arbitrário na URL."""

    full_name: str

    def __post_init__(self) -> None:
        if not _REPO.fullmatch(self.full_name):
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
    ) -> None:
        self._token = token
        self._http = http_client
        self._api_url = api_url.rstrip("/")
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token.get_secret_value()}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": USER_AGENT,
        }

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        try:
            response = await self._http.request(
                method, url, headers=self._headers(), timeout=self._timeout, **kwargs
            )
        except httpx.HTTPError:
            raise GithubError(GithubErrorCode.NETWORK) from None
        _raise_for_status(response)
        return response

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
        url = f"{self._api_url}/repos/{repo.full_name}/issues"
        data = _json(await self._request("POST", url, json={"title": title, "body": body}))
        if not isinstance(data, dict):
            raise GithubError(GithubErrorCode.INVALID_RESPONSE)
        return data


def _json(response: httpx.Response) -> object:
    try:
        return response.json()
    except ValueError:
        raise GithubError(GithubErrorCode.INVALID_RESPONSE) from None


def _next_link(response: httpx.Response) -> str | None:
    match = _NEXT_LINK.search(response.headers.get("link", ""))
    return match.group(1) if match else None


def _raise_for_status(response: httpx.Response) -> None:
    status = response.status_code
    if status < 400:
        return
    if status == 429 or (status == 403 and response.headers.get("x-ratelimit-remaining") == "0"):
        raise GithubError(GithubErrorCode.RATE_LIMITED, status)
    if status in (401, 403):
        raise GithubError(GithubErrorCode.UNAUTHORIZED, status)
    if status == 404:
        raise GithubError(GithubErrorCode.NOT_FOUND, status)
    raise GithubError(GithubErrorCode.HTTP_ERROR, status)
