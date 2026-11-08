"""Fábricas de eventos para os testes do ledger."""

from typing import Any
from uuid import UUID, uuid4

from basho.evidence.contracts import (
    Actor,
    ActorType,
    EventKind,
    EventSource,
    NewEvidenceEvent,
)

TENANT_A = UUID("00000000-0000-0000-0000-0000000000a1")
PROJECT_A = UUID("00000000-0000-0000-0000-0000000000b1")


def make_event(**overrides: Any) -> NewEvidenceEvent:
    """Evento válido e sintético; ``overrides`` sobrescreve campos."""
    fields: dict[str, Any] = {
        "tenant_id": TENANT_A,
        "project_id": PROJECT_A,
        "kind": EventKind.COMMIT_OBSERVED,
        "source": EventSource.GITHUB,
        "source_ref": "abc123",
        "actor": Actor(type=ActorType.SYSTEM, id="system"),
        "payload": {"message": "feat: ledger", "files": 3},
        "supersedes": None,
        "is_synthetic": True,
    }
    fields.update(overrides)
    return NewEvidenceEvent(**fields)


def fresh_ids() -> tuple[UUID, UUID]:
    """Par (tenant_id, project_id) novo, para isolar testes de banco entre si."""
    return uuid4(), uuid4()
