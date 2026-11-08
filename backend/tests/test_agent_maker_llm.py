"""Chamada **real** ao Claude. Fora do CI: só roda com `RUN_LLM_TESTS=1` e `-m llm`.

Gasta tokens de verdade: rode à mão, com dados sintéticos, para conferir que a API aceita a
requisição do Maker (parâmetros, tools, cache) e que a saída passa no schema.
"""

import os
from uuid import uuid4

import anthropic
import pytest

from basho.agent.approvals import InMemoryApprovalStore
from basho.agent.checks import ReportDeterministicChecker
from basho.agent.maker import Maker, MakerStatus, MakerTask
from basho.agent.policy import ToolPolicy
from basho.agent.simulated_tools import build_simulated_registry
from basho.agent.tasks import RESEARCH_REPORT_PROFILE
from basho.audit import InMemoryAuditLog
from evidence_factories import PROJECT_A, TENANT_A
from maker_support import FixedVerifier, InMemoryEvidence, report_input
from report_factories import commit, report
from tool_support import github_fixtures

pytestmark = [
    pytest.mark.llm,
    pytest.mark.skipif(
        os.environ.get("RUN_LLM_TESTS") != "1", reason="chamada real ao Claude: RUN_LLM_TESTS=1"
    ),
]


async def test_real_claude_returns_a_schema_valid_research_report() -> None:
    # Arrange
    evidence = commit()
    template = report(method_ids=(evidence.id,), result_ids=(evidence.id,))
    registry = build_simulated_registry(github_fixtures())
    maker = Maker(
        client=anthropic.AsyncAnthropic(),
        registry=registry,
        policy=ToolPolicy(registry, InMemoryAuditLog(), InMemoryApprovalStore()),
        checker=ReportDeterministicChecker(TENANT_A),
        verifier=FixedVerifier(),
        evidence=InMemoryEvidence([evidence]),
    )

    # Act
    result = await maker.run(
        MakerTask(
            tenant_id=TENANT_A,
            run_id=uuid4(),
            project_id=PROJECT_A,
            profile=RESEARCH_REPORT_PROFILE,
            task_input=report_input(template),
            is_synthetic=True,
        )
    )

    # Assert: a saída passou no schema (pode terminar em draft se citar mal)
    assert result.status in {MakerStatus.COMPLETED, MakerStatus.INVALID_OUTPUT}
    assert all(call.model.startswith("claude-") for call in result.calls)
