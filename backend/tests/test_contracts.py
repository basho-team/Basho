"""Testes de contrato (#20): fixtures e invariantes dos schemas compartilhados."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from basho.agent.artifacts import ActivityRecordDraft, Claim, ClaimSection
from basho.agent.tools import AGENT_ALLOWED_LEVELS, MVP_TOOLS, PermissionLevel, ToolSpec
from basho.evidence.contracts import (
    Actor,
    ActorType,
    EventKind,
    EventSource,
    NewEvidenceEvent,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_activity_record_fixture_matches_maker_contract() -> None:
    # Arrange
    raw = json.loads(
        (FIXTURES / "activity_record_draft.json").read_text(encoding="utf-8")
    )

    # Act
    draft = ActivityRecordDraft.model_validate(raw)

    # Assert
    assert all(claim.evidence_ids for claim in draft.claims)
    assert draft.formal_hours_event_ids == ()


def test_claim_without_evidence_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Claim(
            section=ClaimSection.RESULT,
            text="Resultado sem nenhuma citação.",
            evidence_ids=(),
        )


def test_mvp_tools_never_include_formal_level() -> None:
    assert all(level in AGENT_ALLOWED_LEVELS for level in MVP_TOOLS.values())
    assert PermissionLevel.FORMAL not in AGENT_ALLOWED_LEVELS


def test_tool_spec_requires_level() -> None:
    with pytest.raises(ValidationError):
        ToolSpec.model_validate(
            {
                "name": "github_list_commits",
                "description": "Lista commits",
                "input_schema": {},
            }
        )


def test_evidence_event_is_immutable() -> None:
    # Arrange
    event = NewEvidenceEvent(
        tenant_id=uuid4(),
        project_id=uuid4(),
        kind=EventKind.COMMIT_OBSERVED,
        source=EventSource.GITHUB,
        source_ref="a1f3c9e",
        actor=Actor(type=ActorType.SYSTEM, id="system"),
        payload={"message": "exp"},
        is_synthetic=True,
    )

    # Act / Assert
    with pytest.raises(ValidationError):
        event.payload = {}


def test_github_fixtures_are_marked_synthetic() -> None:
    for name in ("commits.json", "pull_requests.json"):
        items = json.loads((FIXTURES / "github" / name).read_text(encoding="utf-8"))
        assert items and all(item["_synthetic"] is True for item in items)
