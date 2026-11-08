"""`ledger_query_events` real, sobre o `EvidenceService` (ADR-0001: só o service público).

A tool é presa ao projeto da tarefa: o modelo não lê eventos de outro projeto do tenant
(minimização, ADR-0006). `data` traz só identificadores; `source_ref` e `payload` (mensagens de
commit, corpos de PR...) vêm de fonte externa e saem em `untrusted_data`.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from basho.agent.tools import MVP_TOOLS, ToolCallStatus, ToolResult, ToolSpec
from basho.evidence import EvidenceNotFoundError, EvidenceService
from basho.evidence.contracts import (
    FORMAL_DATA_KINDS,
    EventKind,
    EventSource,
    EvidenceEvent,
    NewEvidenceEvent,
)

MAX_EVENTS = 100
DEFAULT_EVENTS = 50
PROJECT_NOT_ALLOWED = "project_not_allowed"
INVALID_ARGUMENTS = "invalid_arguments"


class QueryEventsArgs(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    project_id: UUID
    kinds: tuple[EventKind, ...] | None = None
    limit: int = Field(default=DEFAULT_EVENTS, ge=1, le=MAX_EVENTS)


class LedgerQueryEvents:
    spec = ToolSpec(
        name="ledger_query_events",
        description=(
            "Consulta eventos do ledger do projeto (commits, PRs, horas formais...). "
            "Use os `id` devolvidos como evidence_ids."
        ),
        level=MVP_TOOLS["ledger_query_events"],
        input_schema=QueryEventsArgs.model_json_schema(),
    )

    def __init__(self, evidence: EvidenceService, project_id: UUID) -> None:
        self._evidence = evidence
        self._project_id = project_id

    async def run(self, tenant_id: str, arguments: dict[str, Any]) -> ToolResult:
        try:
            args = QueryEventsArgs.model_validate(arguments)
        except ValidationError:
            return self._error(INVALID_ARGUMENTS)
        if args.project_id != self._project_id:
            return self._error(PROJECT_NOT_ALLOWED)
        queried = await self._evidence.query(
            UUID(tenant_id), project_id=args.project_id, kinds=args.kinds, limit=args.limit
        )
        events = [event for event in queried if is_citable(event)]
        return ToolResult(
            tool=self.spec.name,
            status=ToolCallStatus.OK,
            data={
                "events": [
                    {
                        "id": str(event.id),
                        "kind": event.kind.value,
                        "source": event.source.value,
                        "created_at": event.created_at.isoformat(),
                        "is_synthetic": event.is_synthetic,
                    }
                    for event in events
                ]
            },
            untrusted_data=json.dumps(
                [_untrusted_view(event) for event in events], ensure_ascii=False, sort_keys=True
            ),
        )

    def _error(self, code: str) -> ToolResult:
        return ToolResult(tool=self.spec.name, status=ToolCallStatus.ERROR, error=code)


def is_citable(event: EvidenceEvent) -> bool:
    """Evidência é fato observado ou declarado. Eventos `source=agent` (rascunhos do Maker,
    vereditos do Checker) não sustentam claims: citá-los seria evidência circular."""
    return event.source is not EventSource.AGENT


def _untrusted_view(event: EvidenceEvent) -> dict[str, Any]:
    """Conteúdo do evento para o modelo. Dados formais (horas, dispêndio: pessoas e valores)
    não vão ao LLM (LGPD, ADR-0006 §3): o Maker só precisa do `id` para citá-los."""
    if event.kind in FORMAL_DATA_KINDS:
        return {"id": str(event.id), "payload_omitted": "formal_data"}
    return {"id": str(event.id), "source_ref": event.source_ref, "payload": event.payload}


class LedgerEvidenceGateway:
    """`EvidenceGateway` do Maker sobre o `EvidenceService` (transação do chamador)."""

    def __init__(self, evidence: EvidenceService) -> None:
        self._evidence = evidence

    async def get_many(
        self, tenant_id: UUID, project_id: UUID, ids: Sequence[UUID]
    ) -> list[EvidenceEvent]:
        """Eventos citados que existem neste tenant **e neste projeto** e são citáveis (não
        `source=agent`). Os demais ficam de fora, e o check determinístico os aponta como
        `unknown_evidence` — inclusive um id que tenha chegado ao modelo por conteúdo externo."""
        found: list[EvidenceEvent] = []
        for event_id in dict.fromkeys(ids):
            try:
                event = await self._evidence.get(tenant_id, event_id)
            except EvidenceNotFoundError:
                continue
            if event.project_id == project_id and is_citable(event):
                found.append(event)
        return found

    async def append(self, event: NewEvidenceEvent) -> EvidenceEvent:
        return await self._evidence.append(event)
