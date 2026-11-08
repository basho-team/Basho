"""Ingestão de commits e PRs do GitHub no Evidence Ledger (#7, ADR-0003/0006).

Cada item vira um evento `source=github` com `source_ref` estável (`owner/repo@sha`,
`owner/repo#número`). Reexecutar não duplica: refs já registradas são puladas, e um advisory
lock por tenant+projeto+repositório serializa execuções concorrentes. O payload guarda só o
necessário (LGPD): login do autor, sem e-mail nem nome.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from basho.connectors.github.client import GithubClient, RepoRef
from basho.evidence import EvidenceService
from basho.evidence.contracts import Actor, ActorType, EventKind, EventSource, NewEvidenceEvent

CONNECTOR_ACTOR = Actor(type=ActorType.SYSTEM, id="github-connector")
MAX_TEXT_CHARS = 20_000
"""Corpo de PR e mensagem de commit são truncados: dado externo sem limite vira risco."""


@dataclass(frozen=True)
class IngestResult:
    created: int
    skipped: int


def commit_ref(repo: RepoRef, sha: str) -> str:
    return f"{repo.full_name}@{sha}"


def pull_request_ref(repo: RepoRef, number: int) -> str:
    return f"{repo.full_name}#{number}"


def _text(value: object) -> str:
    return value[:MAX_TEXT_CHARS] if isinstance(value, str) else ""


def _login(user: object) -> str | None:
    if isinstance(user, dict) and isinstance(user.get("login"), str):
        return str(user["login"])
    return None


def commit_payload(repo: RepoRef, item: dict[str, Any]) -> dict[str, Any] | None:
    sha = item.get("sha")
    commit = item.get("commit")
    if not isinstance(sha, str) or not isinstance(commit, dict):
        return None
    author = commit.get("author") if isinstance(commit.get("author"), dict) else {}
    return {
        "repo": repo.full_name,
        "sha": sha,
        "message": _text(commit.get("message")),
        "author_login": _login(item.get("author")),
        "committed_at": author.get("date") if isinstance(author, dict) else None,
    }


def pull_request_payload(repo: RepoRef, item: dict[str, Any]) -> dict[str, Any] | None:
    number = item.get("number")
    if not isinstance(number, int) or isinstance(number, bool):
        return None
    return {
        "repo": repo.full_name,
        "number": number,
        "title": _text(item.get("title")),
        "body": _text(item.get("body")),
        "state": item.get("state") if isinstance(item.get("state"), str) else None,
        "created_at": item.get("created_at"),
        "merged_at": item.get("merged_at"),
        "author_login": _login(item.get("user")),
    }


class GithubIngestService:
    def __init__(self, session: AsyncSession, client: GithubClient) -> None:
        self._session = session
        self._client = client
        self._ledger = EvidenceService(session)

    async def sync(
        self,
        tenant_id: UUID,
        project_id: UUID,
        repo: RepoRef,
        *,
        since: datetime | None = None,
        limit: int = 100,
        is_synthetic: bool = False,
    ) -> IngestResult:
        """Lê commits e PRs e grava os que faltam. Roda dentro de `tenant_session`."""
        await self._lock(tenant_id, project_id, repo)
        commits = await self._client.list_commits(repo, since=since, limit=limit)
        pulls = await self._client.list_pull_requests(repo, limit=limit)
        items = [
            *(
                (EventKind.COMMIT_OBSERVED, commit_ref(repo, p["sha"]), p)
                for p in filter(None, (commit_payload(repo, c) for c in commits))
            ),
            *(
                (EventKind.PULL_REQUEST_OBSERVED, pull_request_ref(repo, p["number"]), p)
                for p in filter(None, (pull_request_payload(repo, pr) for pr in pulls))
            ),
        ]
        known = await self._ledger.existing_source_refs(
            tenant_id, project_id, EventSource.GITHUB, (ref for _, ref, _ in items)
        )
        created = 0
        for kind, ref, payload in _unique(items):
            if ref in known:
                continue
            await self._ledger.append(
                NewEvidenceEvent(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    kind=kind,
                    source=EventSource.GITHUB,
                    source_ref=ref,
                    actor=CONNECTOR_ACTOR,
                    payload=payload,
                    is_synthetic=is_synthetic,
                )
            )
            created += 1
        return IngestResult(created=created, skipped=len(items) - created)

    async def _lock(self, tenant_id: UUID, project_id: UUID, repo: RepoRef) -> None:
        key = f"github-ingest:{tenant_id}:{project_id}:{repo.full_name}"
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": key}
        )


def _unique(
    items: Iterable[tuple[EventKind, str, dict[str, Any]]],
) -> list[tuple[EventKind, str, dict[str, Any]]]:
    seen: set[str] = set()
    result = []
    for item in items:
        if item[1] not in seen:
            seen.add(item[1])
            result.append(item)
    return result
