"""Registro de tools: falha rápida na inicialização (ADR-0005)."""

import pytest

from basho.agent.registry import ToolRegistrationError, ToolRegistry
from basho.agent.simulated_tools import build_simulated_registry
from basho.agent.tasks import RESEARCH_REPORT_PROFILE, validate_allowlist
from basho.agent.tools import AGENT_ALLOWED_LEVELS, MVP_TOOLS, PermissionLevel, ToolSpec
from tool_support import FakeTool, github_fixtures, make_spec


def test_tool_without_level_is_refused_at_startup() -> None:
    # Arrange: spec construída sem validação e sem `level`
    spec = ToolSpec.model_construct(  # type: ignore[call-arg]
        name="tool_sem_nivel", description="tool sem nível declarado", input_schema={}
    )

    # Act / Assert
    with pytest.raises(ToolRegistrationError, match="level"):
        ToolRegistry([FakeTool(spec)])


def test_object_without_tool_spec_is_refused() -> None:
    # Arrange
    class NotATool:
        spec = ("dict_tool", "read")

    # Act / Assert
    with pytest.raises(ToolRegistrationError, match="ToolSpec"):
        ToolRegistry([NotATool()])  # type: ignore[list-item]


def test_formal_tool_is_never_registered_for_the_agent() -> None:
    # Arrange
    formal = FakeTool(make_spec("approve_record", PermissionLevel.FORMAL))

    # Act / Assert
    with pytest.raises(ToolRegistrationError, match="formal"):
        ToolRegistry([formal])


def test_duplicate_tool_name_is_refused() -> None:
    # Arrange
    tool = FakeTool(make_spec("custom_read", PermissionLevel.READ))

    # Act / Assert
    with pytest.raises(ToolRegistrationError, match="já registrada"):
        ToolRegistry([tool, tool])


def test_level_diverging_from_contract_is_refused() -> None:
    # Arrange: github_create_issue é external no contrato
    downgraded = FakeTool(make_spec("github_create_issue", PermissionLevel.READ))

    # Act / Assert
    with pytest.raises(ToolRegistrationError, match="contrato exige external"):
        ToolRegistry([downgraded])


def test_simulated_registry_implements_every_mvp_tool_with_contract_level() -> None:
    # Act
    registry = build_simulated_registry(github_fixtures())

    # Assert
    assert dict(registry.levels()) == MVP_TOOLS
    assert validate_allowlist(RESEARCH_REPORT_PROFILE.allowed_tools, registry.levels())


def test_specs_for_profile_expose_only_allowlisted_non_formal_tools() -> None:
    # Arrange
    registry = build_simulated_registry(github_fixtures())

    # Act
    specs = registry.specs_for(RESEARCH_REPORT_PROFILE)

    # Assert
    names = {spec.name for spec in specs}
    assert names == RESEARCH_REPORT_PROFILE.allowed_tools
    assert "github_create_issue" not in names
    assert all(spec.level in AGENT_ALLOWED_LEVELS for spec in specs)
    assert all(spec.level is not PermissionLevel.FORMAL for spec in specs)
