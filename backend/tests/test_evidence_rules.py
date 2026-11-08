"""Testes unitários das regras de domínio do ledger (sem banco)."""

from typing import Any
from uuid import uuid4

import pytest

from basho.evidence.contracts import (
    Actor,
    ActorType,
    EventKind,
    EventSource,
)
from basho.evidence.domain.rules import (
    AGENT_ACTOR_IDS,
    EvidenceValidationError,
    validate_event_shape,
    validate_supersedes_target,
)
from evidence_factories import make_event

USER = Actor(type=ActorType.USER, id="u1")
SYSTEM = Actor(type=ActorType.SYSTEM, id="system")
MAKER = Actor(type=ActorType.AGENT, id="maker", model="claude-sonnet-5-5")
CHECKER = Actor(type=ActorType.AGENT, id="checker", model="other-model")

FORMAL = EventKind.FORMAL_HOURS_DECLARED
EXPENSE = EventKind.EXPENSE_DECLARED
CORRECTION = EventKind.USER_CORRECTION
CONFIRMATION = EventKind.USER_CONFIRMATION
COMMIT = EventKind.COMMIT_OBSERVED

# (kind, source, actor, tem supersedes) aceitas
ACCEPTED: list[tuple[EventKind, EventSource, Actor, bool]] = [
    (FORMAL, EventSource.USER, USER, False),
    (EXPENSE, EventSource.USER, USER, False),
    (FORMAL, EventSource.FORMAL_SYSTEM, USER, False),
    (FORMAL, EventSource.FORMAL_SYSTEM, SYSTEM, False),
    (EXPENSE, EventSource.FORMAL_SYSTEM, SYSTEM, False),
    (CORRECTION, EventSource.USER, USER, True),
    (CONFIRMATION, EventSource.USER, USER, False),
    (COMMIT, EventSource.GITHUB, SYSTEM, False),
    (COMMIT, EventSource.SYSTEM, SYSTEM, False),
    (COMMIT, EventSource.USER, USER, False),
    (EventKind.TECHNICAL_JUSTIFICATION, EventSource.AGENT, MAKER, False),
    (EventKind.VERIFICATION_RESULT, EventSource.AGENT, CHECKER, False),
]

# (kind, source, actor, tem supersedes, trecho esperado da mensagem) rejeitadas
REJECTED: list[tuple[EventKind, EventSource, Actor, bool, str]] = [
    (FORMAL, EventSource.USER, MAKER, False, "source 'agent'"),
    (FORMAL, EventSource.AGENT, MAKER, False, "dados formais"),
    (FORMAL, EventSource.GITHUB, SYSTEM, False, "dados formais"),
    (FORMAL, EventSource.SYSTEM, SYSTEM, False, "dados formais"),
    (FORMAL, EventSource.USER, SYSTEM, False, "source 'user'"),
    (FORMAL, EventSource.FORMAL_SYSTEM, MAKER, False, "source 'agent'"),
    (CORRECTION, EventSource.AGENT, MAKER, True, "correção"),
    (CORRECTION, EventSource.SYSTEM, SYSTEM, True, "correção"),
    (CORRECTION, EventSource.USER, USER, False, "supersedes"),
    (CONFIRMATION, EventSource.SYSTEM, SYSTEM, False, "confirmação"),
    (CONFIRMATION, EventSource.AGENT, MAKER, False, "confirmação"),
    (COMMIT, EventSource.AGENT, SYSTEM, False, "source 'agent'"),
    (COMMIT, EventSource.GITHUB, MAKER, False, "source 'agent'"),
    (COMMIT, EventSource.USER, SYSTEM, False, "source 'user'"),
    (COMMIT, EventSource.USER, MAKER, False, "source 'agent'"),
]


def _event(kind: EventKind, source: EventSource, actor: Actor, *, supersedes: bool) -> Any:
    return make_event(
        kind=kind, source=source, actor=actor, supersedes=uuid4() if supersedes else None
    )


@pytest.mark.parametrize(("kind", "source", "actor", "supersedes"), ACCEPTED)
def test_accepted_actor_source_kind_combinations(
    kind: EventKind, source: EventSource, actor: Actor, supersedes: bool
) -> None:
    validate_event_shape(_event(kind, source, actor, supersedes=supersedes))


@pytest.mark.parametrize(("kind", "source", "actor", "supersedes", "reason"), REJECTED)
def test_rejected_actor_source_kind_combinations(
    kind: EventKind, source: EventSource, actor: Actor, supersedes: bool, reason: str
) -> None:
    with pytest.raises(EvidenceValidationError, match=reason):
        validate_event_shape(_event(kind, source, actor, supersedes=supersedes))


@pytest.mark.parametrize("actor_id", ["maker2", "user", "system", "Maker"])
def test_agent_actor_with_unknown_id_is_rejected(actor_id: str) -> None:
    actor = Actor(type=ActorType.AGENT, id=actor_id, model="m")
    event = make_event(source=EventSource.AGENT, actor=actor)

    with pytest.raises(EvidenceValidationError, match="maker"):
        validate_event_shape(event)


def test_agent_actor_ids_are_maker_and_checker() -> None:
    assert frozenset({"maker", "checker"}) == AGENT_ACTOR_IDS


def test_agent_actor_without_model_is_rejected() -> None:
    event = make_event(source=EventSource.AGENT, actor=Actor(type=ActorType.AGENT, id="maker"))

    with pytest.raises(EvidenceValidationError, match="model"):
        validate_event_shape(event)


_NUL = "a\x00b"
NUL_CASES: list[dict[str, Any]] = [
    {"payload": {"k": _NUL}},
    {"payload": {_NUL: 1}},
    {"payload": {"a": {"b": [1, {"c": _NUL}]}}},
    {"source_ref": _NUL},
    {"actor": Actor(type=ActorType.SYSTEM, id=_NUL)},
    {"actor": Actor(type=ActorType.SYSTEM, id="system", model=_NUL)},
]


@pytest.mark.parametrize("overrides", NUL_CASES)
def test_nul_character_anywhere_in_text_is_rejected(overrides: dict[str, Any]) -> None:
    event = make_event(**overrides)

    with pytest.raises(EvidenceValidationError, match="U\\+0000"):
        validate_event_shape(event)


def test_validation_does_not_alter_payload_content() -> None:
    event = make_event(payload={"texto": "ação", "n": [1, 2]})

    validate_event_shape(event)

    assert event.payload == {"texto": "ação", "n": [1, 2]}


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
