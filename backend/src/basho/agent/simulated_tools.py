"""Implementações **simuladas** das tools do MVP (até a integração com #7 e o ledger real).

As tools GitHub leem dados sintéticos já carregados (fixtures de `tests/fixtures/github`); as
tools internas guardam em memória. Tudo devolvido é marcado `is_synthetic`. Texto livre vindo
de fonte externa (mensagens, títulos, corpos de PR, autores) sai só em `untrusted_data`; `data`
carrega apenas identificadores e campos estruturados.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from basho.agent.registry import ToolRegistry
from basho.agent.tools import MVP_TOOLS, PermissionLevel, ToolCallStatus, ToolResult, ToolSpec

MAX_LIST_LIMIT = 100
DEFAULT_LIST_LIMIT = 50
INVALID_ARGUMENTS = "invalid_arguments"


class _Args(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


def _spec(name: str, description: str, args: type[_Args], **extra: Any) -> ToolSpec:
    return ToolSpec(
        name=name,
        description=description,
        level=MVP_TOOLS[name],
        input_schema=args.model_json_schema(),
        **extra,
    )


def _invalid(tool: str) -> ToolResult:
    # Sem detalhes do Pydantic: a mensagem ecoaria a entrada (possível PII).
    return ToolResult(tool=tool, status=ToolCallStatus.ERROR, error=INVALID_ARGUMENTS)


def _untrusted(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


class GithubFixtures(BaseModel):
    """Dados sintéticos do GitHub (listas cruas como nas fixtures)."""

    model_config = ConfigDict(frozen=True)

    commits: tuple[dict[str, Any], ...]
    pull_requests: tuple[dict[str, Any], ...]

    @classmethod
    def load(cls, directory: Path) -> GithubFixtures:
        def read(name: str) -> tuple[dict[str, Any], ...]:
            items = json.loads((directory / name).read_text(encoding="utf-8"))
            if not all(item.get("_synthetic") is True for item in items):
                msg = f"{name}: toda fixture precisa ser marcada _synthetic"
                raise ValueError(msg)
            return tuple(items)

        return cls(commits=read("commits.json"), pull_requests=read("pull_requests.json"))


class ListCommitsArgs(_Args):
    since: datetime | None = None
    until: datetime | None = None
    limit: int = Field(default=DEFAULT_LIST_LIMIT, ge=1, le=MAX_LIST_LIMIT)


class GithubListCommits:
    spec = _spec(
        "github_list_commits",
        "Lista commits do repositório do projeto (sha e data; mensagem como dado externo).",
        ListCommitsArgs,
    )

    def __init__(self, fixtures: GithubFixtures) -> None:
        self._fixtures = fixtures

    async def run(self, tenant_id: str, arguments: dict[str, Any]) -> ToolResult:
        try:
            args = ListCommitsArgs.model_validate(arguments)
        except ValidationError:
            return _invalid(self.spec.name)
        selected = [
            commit
            for commit in self._fixtures.commits
            if (args.since is None or _parse(commit["date"]) >= args.since)
            and (args.until is None or _parse(commit["date"]) <= args.until)
        ][: args.limit]
        return ToolResult(
            tool=self.spec.name,
            status=ToolCallStatus.OK,
            data={
                "is_synthetic": True,
                "commits": [{"sha": c["sha"], "date": c["date"]} for c in selected],
            },
            untrusted_data=_untrusted(
                [
                    {"sha": c["sha"], "author": c["author"], "message": c["message"]}
                    for c in selected
                ]
            ),
        )


class GetPullRequestArgs(_Args):
    number: int = Field(ge=1)


class GithubGetPullRequest:
    spec = _spec(
        "github_get_pull_request",
        "Lê um pull request (estado, datas, commits; título e corpo como dado externo).",
        GetPullRequestArgs,
    )

    def __init__(self, fixtures: GithubFixtures) -> None:
        self._fixtures = fixtures

    async def run(self, tenant_id: str, arguments: dict[str, Any]) -> ToolResult:
        try:
            args = GetPullRequestArgs.model_validate(arguments)
        except ValidationError:
            return _invalid(self.spec.name)
        found = next(
            (pr for pr in self._fixtures.pull_requests if pr["number"] == args.number), None
        )
        if found is None:
            return ToolResult(
                tool=self.spec.name, status=ToolCallStatus.ERROR, error="pull_request_not_found"
            )
        return ToolResult(
            tool=self.spec.name,
            status=ToolCallStatus.OK,
            data={
                "is_synthetic": True,
                "number": found["number"],
                "state": found["state"],
                "created_at": found["created_at"],
                "merged_at": found["merged_at"],
                "commits": list(found["commits"]),
            },
            untrusted_data=_untrusted(
                {
                    "title": found["title"],
                    "body": found["body"],
                    "user": found["user"],
                    "labels": found["labels"],
                }
            ),
        )


class SimulatedInternalStore:
    """Rascunhos e pendências em memória, por tenant (substituído pelo ledger/projeções)."""

    def __init__(self) -> None:
        self.records: dict[str, list[dict[str, Any]]] = {}

    def append(self, tenant_id: str, record: dict[str, Any]) -> dict[str, Any]:
        saved = {**record, "id": str(uuid4()), "created_at": datetime.now(UTC).isoformat()}
        self.records.setdefault(tenant_id, []).append(saved)
        return saved

    def of(self, tenant_id: str) -> Sequence[dict[str, Any]]:
        return tuple(self.records.get(tenant_id, ()))


_EVENT_IDENTIFIERS = ("id", "kind", "project_id", "created_at")
_EVENT_ID_ONLY = frozenset({"kind", "project_id", "created_at"})


class QueryEventsArgs(_Args):
    project_id: UUID
    kinds: tuple[str, ...] | None = None
    limit: int = Field(default=DEFAULT_LIST_LIMIT, ge=1, le=MAX_LIST_LIMIT)


class LedgerQueryEvents:
    spec = _spec(
        "ledger_query_events",
        "Consulta eventos do ledger do projeto (simulado: registros internos em memória).",
        QueryEventsArgs,
    )

    def __init__(self, store: SimulatedInternalStore) -> None:
        self._store = store

    async def run(self, tenant_id: str, arguments: dict[str, Any]) -> ToolResult:
        try:
            args = QueryEventsArgs.model_validate(arguments)
        except ValidationError:
            return _invalid(self.spec.name)
        events = [
            event
            for event in self._store.of(tenant_id)
            if event["project_id"] == str(args.project_id)
            and (args.kinds is None or event["kind"] in args.kinds)
        ][: args.limit]
        # Rascunhos e pendências podem conter texto copiado de fonte externa (injeção de segunda
        # ordem): só identificadores em `data`; o conteúdo volta como dado não confiável.
        return ToolResult(
            tool=self.spec.name,
            status=ToolCallStatus.OK,
            data={
                "is_synthetic": True,
                "events": [{key: event[key] for key in _EVENT_IDENTIFIERS} for event in events],
            },
            untrusted_data=_untrusted(
                [
                    {key: value for key, value in event.items() if key not in _EVENT_ID_ONLY}
                    | {"id": event["id"]}
                    for event in events
                ]
            ),
        )


class RecordDraftArgs(_Args):
    project_id: UUID
    draft: dict[str, Any] = Field(description="Rascunho estruturado do Maker (validado em #8/#9)")


class LedgerRecordDraft:
    spec = _spec(
        "ledger_record_draft",
        "Registra um rascunho do Maker como registro interno (nunca formal).",
        RecordDraftArgs,
    )

    def __init__(self, store: SimulatedInternalStore) -> None:
        self._store = store

    async def run(self, tenant_id: str, arguments: dict[str, Any]) -> ToolResult:
        try:
            args = RecordDraftArgs.model_validate(arguments)
        except ValidationError:
            return _invalid(self.spec.name)
        saved = self._store.append(
            tenant_id,
            {"kind": "draft", "project_id": str(args.project_id), "draft": args.draft},
        )
        return ToolResult(
            tool=self.spec.name,
            status=ToolCallStatus.OK,
            data={"is_synthetic": True, "draft_id": saved["id"]},
        )


class OpenPendingArgs(_Args):
    project_id: UUID
    title: str = Field(min_length=5, max_length=200)
    question: str = Field(min_length=10, max_length=1000, description="Pergunta objetiva")
    assignee_role: str = Field(pattern=r"^[a-z][a-z_]{2,31}$")


class PendingItemOpen:
    spec = _spec(
        "pending_item_open",
        "Abre uma pendência com pergunta objetiva para o responsável (registro interno).",
        OpenPendingArgs,
    )

    def __init__(self, store: SimulatedInternalStore) -> None:
        self._store = store

    async def run(self, tenant_id: str, arguments: dict[str, Any]) -> ToolResult:
        try:
            args = OpenPendingArgs.model_validate(arguments)
        except ValidationError:
            return _invalid(self.spec.name)
        saved = self._store.append(
            tenant_id, {"kind": "pending_item", **args.model_dump(mode="json")}
        )
        return ToolResult(
            tool=self.spec.name,
            status=ToolCallStatus.OK,
            data={"is_synthetic": True, "pending_item_id": saved["id"]},
        )


class CreateIssueArgs(_Args):
    title: str = Field(min_length=5, max_length=200)
    body: str = Field(max_length=5000)


class GithubCreateIssue:
    """Simulada: não chama o GitHub. Só roda após aprovação humana (worker, #10)."""

    spec = _spec(
        "github_create_issue",
        "Cria issue no GitHub do projeto. Ação externa: exige aprovação humana.",
        CreateIssueArgs,
        requires_approval=True,
    )

    def __init__(self) -> None:
        self.created: list[CreateIssueArgs] = []

    async def run(self, tenant_id: str, arguments: dict[str, Any]) -> ToolResult:
        try:
            args = CreateIssueArgs.model_validate(arguments)
        except ValidationError:
            return _invalid(self.spec.name)
        self.created.append(args)
        return ToolResult(
            tool=self.spec.name,
            status=ToolCallStatus.OK,
            data={"is_synthetic": True, "simulated": True, "issue_number": len(self.created)},
        )


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value)


def build_simulated_registry(
    fixtures: GithubFixtures, store: SimulatedInternalStore | None = None
) -> ToolRegistry:
    """Registro com as seis tools do MVP, todas simuladas."""
    internal = store if store is not None else SimulatedInternalStore()
    registry = ToolRegistry(
        [
            GithubListCommits(fixtures),
            GithubGetPullRequest(fixtures),
            LedgerQueryEvents(internal),
            LedgerRecordDraft(internal),
            PendingItemOpen(internal),
            GithubCreateIssue(),
        ]
    )
    missing: Mapping[str, PermissionLevel] = {
        name: level for name, level in MVP_TOOLS.items() if registry.get(name) is None
    }
    if missing:
        msg = f"tools do MVP sem implementação: {sorted(missing)}"
        raise RuntimeError(msg)
    return registry
