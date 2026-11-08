"""Tools reais do GitHub para o Maker, com a mesma spec das simuladas (#6/#7).

O repositório vem da configuração do projeto, nunca do modelo: o Maker só escolhe filtros.
Texto do GitHub (mensagens, títulos, corpos, autores) sai só em `untrusted_data`; `data` leva
identificadores. `github_create_issue` é `external` com `requires_approval`: a `ToolPolicy`
não a executa sem decisão humana (ADR-0005).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from pydantic import ValidationError

from basho.agent import simulated_tools as simulated
from basho.agent.tools import ToolCallStatus, ToolResult, ToolSpec
from basho.connectors.github.client import GithubClient, GithubError, RepoRef
from basho.connectors.github.ingest import commit_payload, pull_request_payload
from basho.logging import get_logger

_log = get_logger(__name__)


def _untrusted(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _error(tool: str, code: str) -> ToolResult:
    return ToolResult(tool=tool, status=ToolCallStatus.ERROR, error=code)


class GithubListCommitsTool:
    spec: ToolSpec = simulated.GithubListCommits.spec

    def __init__(self, client: GithubClient, repo: RepoRef) -> None:
        self._client = client
        self._repo = repo

    async def run(self, tenant_id: str, arguments: dict[str, Any]) -> ToolResult:
        try:
            args = simulated.ListCommitsArgs.model_validate(arguments)
        except ValidationError:
            return _error(self.spec.name, simulated.INVALID_ARGUMENTS)
        try:
            raw = await self._client.list_commits(self._repo, since=args.since, limit=args.limit)
        except GithubError as exc:
            return _error(self.spec.name, exc.code.value)
        commits = [
            c
            for c in (commit_payload(self._repo, item) for item in raw)
            if c is not None and (args.until is None or _before(c["committed_at"], args.until))
        ]
        return ToolResult(
            tool=self.spec.name,
            status=ToolCallStatus.OK,
            data={
                "repo": self._repo.full_name,
                "commits": [{"sha": c["sha"], "date": c["committed_at"]} for c in commits],
            },
            untrusted_data=_untrusted(
                [
                    {"sha": c["sha"], "author": c["author_login"], "message": c["message"]}
                    for c in commits
                ]
            ),
        )


class GithubGetPullRequestTool:
    spec: ToolSpec = simulated.GithubGetPullRequest.spec

    def __init__(self, client: GithubClient, repo: RepoRef) -> None:
        self._client = client
        self._repo = repo

    async def run(self, tenant_id: str, arguments: dict[str, Any]) -> ToolResult:
        try:
            args = simulated.GetPullRequestArgs.model_validate(arguments)
        except ValidationError:
            return _error(self.spec.name, simulated.INVALID_ARGUMENTS)
        try:
            raw = await self._client.get_pull_request(self._repo, args.number)
        except GithubError as exc:
            return _error(self.spec.name, exc.code.value)
        pr = pull_request_payload(self._repo, raw)
        if pr is None:
            return _error(self.spec.name, "github_invalid_response")
        return ToolResult(
            tool=self.spec.name,
            status=ToolCallStatus.OK,
            data={
                "repo": self._repo.full_name,
                "number": pr["number"],
                "state": pr["state"],
                "created_at": pr["created_at"],
                "merged_at": pr["merged_at"],
            },
            untrusted_data=_untrusted(
                {"title": pr["title"], "body": pr["body"], "user": pr["author_login"]}
            ),
        )


class GithubCreateIssueTool:
    """Ação externa real. Só roda depois da aprovação humana (a policy garante)."""

    spec: ToolSpec = simulated.GithubCreateIssue.spec

    def __init__(self, client: GithubClient, repo: RepoRef) -> None:
        self._client = client
        self._repo = repo

    async def run(self, tenant_id: str, arguments: dict[str, Any]) -> ToolResult:
        try:
            args = simulated.CreateIssueArgs.model_validate(arguments)
        except ValidationError:
            return _error(self.spec.name, simulated.INVALID_ARGUMENTS)
        key = issue_idempotency_key(tenant_id, self._repo, args.title, args.body)
        try:
            issue = await self._client.ensure_issue(
                self._repo, title=args.title, body=args.body, idempotency_key=key
            )
        except GithubError as exc:
            _log.warning(
                "github_create_issue_failed",
                code=exc.code.value,
                attempts=exc.attempts,
                retryable=exc.retryable,
            )
            return _error(self.spec.name, exc.code.value)
        return ToolResult(
            tool=self.spec.name,
            status=ToolCallStatus.OK,
            data={
                "repo": self._repo.full_name,
                "issue_number": issue.number,
                "already_existed": issue.reused,
            },
        )


def issue_idempotency_key(tenant_id: str, repo: RepoRef, title: str, body: str) -> str:
    """Chave estável para a mesma intenção (tenant, repo, título, corpo).

    Vem do conteúdo aprovado, não do modelo: reexecutar a tool depois de uma falha, ou reenviar
    o mesmo pedido, cai na mesma issue em vez de criar outra.
    """
    material = "\x00".join((tenant_id, repo.full_name, title, body))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


def build_github_tools(
    client: GithubClient, repo: RepoRef
) -> tuple[GithubListCommitsTool, GithubGetPullRequestTool, GithubCreateIssueTool]:
    """As três tools GitHub do MVP, presas ao repositório do projeto.

    O chamador (worker, #10) resolve `repo` a partir da configuração do projeto **do tenant
    da sessão**; o `tenant_id` recebido em `run()` não é usado para escolher o repositório.
    """
    return (
        GithubListCommitsTool(client, repo),
        GithubGetPullRequestTool(client, repo),
        GithubCreateIssueTool(client, repo),
    )


def _before(value: object, limit: datetime) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")) <= limit
    except ValueError:
        return False
