"""Helpers dos testes de tools: fixtures GitHub, contexto de chamada e tools de teste."""

from pathlib import Path
from typing import Any
from uuid import uuid4

from basho.agent.policy import ToolCallContext
from basho.agent.simulated_tools import GithubFixtures
from basho.agent.tasks import RESEARCH_REPORT_PROFILE, TaskProfile
from basho.agent.tools import PermissionLevel, ToolCallStatus, ToolResult, ToolSpec

GITHUB_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "github"


def github_fixtures() -> GithubFixtures:
    return GithubFixtures.load(GITHUB_FIXTURES_DIR)


def call_context(profile: TaskProfile = RESEARCH_REPORT_PROFILE) -> ToolCallContext:
    return ToolCallContext(tenant_id=uuid4(), run_id=uuid4(), profile=profile)


def make_spec(name: str, level: PermissionLevel, **extra: Any) -> ToolSpec:
    return ToolSpec(
        name=name,
        description="tool de teste sintética",
        level=level,
        input_schema={"type": "object"},
        **extra,
    )


class FakeTool:
    """Tool de teste que conta execuções e devolve um resultado configurável."""

    def __init__(self, spec: ToolSpec, result: ToolResult | None = None) -> None:
        self.spec = spec
        self.calls: list[dict[str, Any]] = []
        self._result = result

    async def run(self, tenant_id: str, arguments: dict[str, Any]) -> ToolResult:
        self.calls.append(arguments)
        if self._result is not None:
            return self._result
        return ToolResult(tool=self.spec.name, status=ToolCallStatus.OK, data={"ok": True})
