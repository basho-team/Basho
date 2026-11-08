"""Regras de domínio do ledger (funções puras)."""

from typing import Any
from uuid import UUID

from basho.evidence.contracts import (
    FORMAL_DATA_KINDS,
    FORMAL_DATA_SOURCES,
    ActorType,
    EventKind,
    EventSource,
    NewEvidenceEvent,
)

NUL = "\x00"
AGENT_ACTOR_IDS: frozenset[str] = frozenset({"maker", "checker"})
FORMAL_DATA_ACTOR_TYPES: frozenset[ActorType] = frozenset({ActorType.USER, ActorType.SYSTEM})
HUMAN_ONLY_KINDS: frozenset[EventKind] = frozenset(
    {EventKind.USER_CORRECTION, EventKind.USER_CONFIRMATION}
)


class EvidenceError(Exception):
    """Base dos erros de domínio do ledger."""


class EvidenceValidationError(EvidenceError):
    """Evento viola uma regra de domínio. A mensagem não inclui dados do payload."""


class EvidenceNotFoundError(EvidenceError):
    """Evento inexistente no tenant informado."""


def _contains_nul(value: Any) -> bool:
    """True se alguma string (valor ou chave) contém U+0000, que o Postgres rejeita."""
    if isinstance(value, str):
        return NUL in value
    if isinstance(value, dict):
        return any(_contains_nul(key) or _contains_nul(item) for key, item in value.items())
    if isinstance(value, list | tuple):
        return any(_contains_nul(item) for item in value)
    return False


def _validate_text_fields(event: NewEvidenceEvent) -> None:
    actor = event.actor
    if _contains_nul([event.payload, event.source_ref, actor.id, actor.model]):
        raise EvidenceValidationError("texto contém caractere nulo (U+0000)")


def _validate_actor_source(event: NewEvidenceEvent) -> None:
    actor, source = event.actor, event.source
    is_agent_actor = actor.type is ActorType.AGENT
    if is_agent_actor:
        if actor.id not in AGENT_ACTOR_IDS:
            raise EvidenceValidationError("actor agent exige id 'maker' ou 'checker'")
        if not actor.model:
            raise EvidenceValidationError("actor do tipo agent exige o campo model")
    if (source is EventSource.AGENT) != is_agent_actor:
        raise EvidenceValidationError("source 'agent' vale se, e somente se, actor.type = agent")
    if source is EventSource.USER and actor.type is not ActorType.USER:
        raise EvidenceValidationError("source 'user' exige actor.type = user")


def _validate_kind_authority(event: NewEvidenceEvent) -> None:
    actor, source, kind = event.actor, event.source, event.kind
    if kind in FORMAL_DATA_KINDS:
        if source not in FORMAL_DATA_SOURCES:
            message = "dados formais só podem vir de source 'user' ou 'formal_system'"
            raise EvidenceValidationError(message)
        if actor.type not in FORMAL_DATA_ACTOR_TYPES:
            raise EvidenceValidationError("dados formais exigem actor.type user ou system")
        if actor.type is ActorType.SYSTEM and source is not EventSource.FORMAL_SYSTEM:
            raise EvidenceValidationError("actor system só origina dados formais via formal_system")
    if kind in HUMAN_ONLY_KINDS and (
        actor.type is not ActorType.USER or source is not EventSource.USER
    ):
        raise EvidenceValidationError("confirmação e correção exigem actor e source 'user'")
    if kind is EventKind.USER_CORRECTION and event.supersedes is None:
        raise EvidenceValidationError("user_correction exige supersedes")


def validate_event_shape(event: NewEvidenceEvent) -> None:
    """Valida regras que não dependem do banco."""
    _validate_text_fields(event)
    _validate_actor_source(event)
    _validate_kind_authority(event)


def validate_supersedes_target(event: NewEvidenceEvent, target_project_id: UUID | None) -> None:
    """`supersedes` deve apontar para evento do mesmo tenant e projeto.

    ``target_project_id`` é None quando o alvo não existe no tenant.
    """
    if event.supersedes is None:
        return
    if target_project_id is None:
        raise EvidenceValidationError("supersedes não encontrado neste tenant")
    if target_project_id != event.project_id:
        raise EvidenceValidationError("supersedes pertence a outro projeto")
