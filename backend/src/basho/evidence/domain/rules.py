"""Regras de domínio do ledger (funções puras)."""

from uuid import UUID

from basho.evidence.contracts import (
    FORMAL_DATA_KINDS,
    FORMAL_DATA_SOURCES,
    ActorType,
    EventKind,
    NewEvidenceEvent,
)


class EvidenceError(Exception):
    """Base dos erros de domínio do ledger."""


class EvidenceValidationError(EvidenceError):
    """Evento viola uma regra de domínio. A mensagem não inclui dados do payload."""


class EvidenceNotFoundError(EvidenceError):
    """Evento inexistente no tenant informado."""


def validate_event_shape(event: NewEvidenceEvent) -> None:
    """Valida regras que não dependem do banco."""
    if event.kind in FORMAL_DATA_KINDS and event.source not in FORMAL_DATA_SOURCES:
        message = "dados formais só podem vir de source 'user' ou 'formal_system'"
        raise EvidenceValidationError(message)
    if event.actor.type is ActorType.AGENT and not event.actor.model:
        raise EvidenceValidationError("actor do tipo agent exige o campo model")
    if event.kind is EventKind.USER_CORRECTION and event.supersedes is None:
        raise EvidenceValidationError("user_correction exige supersedes")


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
