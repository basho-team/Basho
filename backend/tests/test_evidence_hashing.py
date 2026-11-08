"""Testes unitários do hash canônico (sem banco)."""

import hashlib
import math
from typing import Any
from uuid import UUID

import pytest

from basho.evidence.contracts import (
    Actor,
    ActorType,
    EventKind,
    EventSource,
    NewEvidenceEvent,
)
from basho.evidence.domain.hashing import canonical_json, compute_content_hash
from evidence_factories import PROJECT_A, TENANT_A, make_event


def test_canonical_json_is_independent_of_key_order() -> None:
    # Arrange
    first = {"b": 1, "a": {"y": [1, 2], "x": None}}
    second = {"a": {"x": None, "y": [1, 2]}, "b": 1}

    # Act / Assert
    assert canonical_json(first) == canonical_json(second)
    assert canonical_json(first) == b'{"a":{"x":null,"y":[1,2]},"b":1}'


def test_canonical_json_keeps_unicode_as_utf8() -> None:
    # Act
    encoded = canonical_json({"nome": "ação"})

    # Assert
    assert encoded == '{"nome":"ação"}'.encode()


def test_canonical_json_rejects_nan() -> None:
    with pytest.raises(ValueError, match="Out of range"):
        canonical_json({"valor": math.nan})


def test_content_hash_matches_hand_computed_sha256_of_envelope() -> None:
    # Arrange
    event = make_event()
    canonical = (
        '{"actor":{"id":"system","model":null,"type":"system"},'
        '"is_synthetic":true,"kind":"commit_observed",'
        '"payload":{"files":3,"message":"feat: ledger"},'
        f'"project_id":"{PROJECT_A}","source":"github","source_ref":"abc123",'
        f'"supersedes":null,"tenant_id":"{TENANT_A}"}}'
    )
    expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    # Act
    actual = compute_content_hash(event)

    # Assert
    assert actual == expected
    assert len(actual) == 64


def test_content_hash_ignores_payload_key_order() -> None:
    first = make_event(payload={"a": 1, "b": 2})
    second = make_event(payload={"b": 2, "a": 1})

    assert compute_content_hash(first) == compute_content_hash(second)


_OTHER_ID = UUID("00000000-0000-0000-0000-0000000000c1")
_CHANGES: list[tuple[str, Any]] = [
    ("tenant_id", _OTHER_ID),
    ("project_id", _OTHER_ID),
    ("kind", EventKind.ISSUE_OBSERVED),
    ("source", EventSource.SYSTEM),
    ("source_ref", "def456"),
    ("actor", Actor(type=ActorType.USER, id="u1")),
    ("payload", {"message": "outro"}),
    ("supersedes", _OTHER_ID),
    ("is_synthetic", False),
]


@pytest.mark.parametrize(("field", "value"), _CHANGES, ids=[name for name, _ in _CHANGES])
def test_content_hash_changes_when_any_envelope_field_changes(field: str, value: Any) -> None:
    # Arrange
    base: NewEvidenceEvent = make_event()
    changed = base.model_copy(update={field: value})

    # Act / Assert
    assert compute_content_hash(changed) != compute_content_hash(base)
