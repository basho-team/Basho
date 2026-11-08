"""Testes unitários das regras de domínio do ledger (sem banco)."""

from uuid import uuid4

import pytest

from basho.evidence.contracts import (
    FORMAL_DATA_KINDS,
    FORMAL_DATA_SOURCES,
    Actor,
    ActorType,
    EventKind,
    EventSource,
)
from basho.evidence.domain.rules import (
    EvidenceValidationError,
    validate_event_shape,
    validate_supersedes_target,
)
from evidence_factories import make_event


@pytest.mark.parametrize("kind", sorted(FORMAL_DATA_KINDS))
@pytest.mark.parametrize("source", [s for s in EventSource if s not in FORMAL_DATA_SOURCES])
def test_formal_data_from_non_formal_source_is_rejected(
    kind: EventKind, source: EventSource
) -> None:
    event = make_event(kind=kind, source=source)

    with pytest.raises(EvidenceValidationError, match="dados formais"):
        validate_event_shape(event)


@pytest.mark.parametrize("source", sorted(FORMAL_DATA_SOURCES))
def test_formal_data_from_user_or_formal_system_is_accepted(source: EventSource) -> None:
    event = make_event(kind=EventKind.FORMAL_HOURS_DECLARED, source=source)

    validate_event_shape(event)


def test_agent_actor_without_model_is_rejected() -> None:
    event = make_event(actor=Actor(type=ActorType.AGENT, id="maker"))

    with pytest.raises(EvidenceValidationError, match="model"):
        validate_event_shape(event)


def test_agent_actor_with_model_is_accepted() -> None:
    event = make_event(actor=Actor(type=ActorType.AGENT, id="maker", model="claude-sonnet-5-5"))

    validate_event_shape(event)


def test_user_correction_without_supersedes_is_rejected() -> None:
    event = make_event(kind=EventKind.USER_CORRECTION, source=EventSource.USER)

    with pytest.raises(EvidenceValidationError, match="supersedes"):
        validate_event_shape(event)


def test_user_correction_with_supersedes_is_accepted() -> None:
    event = make_event(kind=EventKind.USER_CORRECTION, source=EventSource.USER, supersedes=uuid4())

    validate_event_shape(event)


def test_supersedes_to_missing_target_is_rejected() -> None:
    event = make_event(supersedes=uuid4())

    with pytest.raises(EvidenceValidationError, match="não encontrado"):
        validate_supersedes_target(event, None)


def test_supersedes_to_other_project_is_rejected() -> None:
    event = make_event(supersedes=uuid4())

    with pytest.raises(EvidenceValidationError, match="outro projeto"):
        validate_supersedes_target(event, uuid4())


def test_supersedes_to_same_project_is_accepted() -> None:
    event = make_event(supersedes=uuid4())

    validate_supersedes_target(event, event.project_id)


def test_event_without_supersedes_skips_target_check() -> None:
    validate_supersedes_target(make_event(), None)
