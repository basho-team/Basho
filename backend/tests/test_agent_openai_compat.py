"""Maker via API compatível com OpenAI (Featherless, ADR-0013). HTTP mockado, sem rede."""

import json
from typing import Any
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from basho.agent.approvals import InMemoryApprovalStore
from basho.agent.checks import ReportDeterministicChecker
from basho.agent.llm import MakerProviderError, ModelSettings
from basho.agent.maker import Maker, MakerStatus, MakerTask
from basho.agent.openai_compat import (
    OpenAICompatibleMessagesClient,
    openai_messages,
    parse_response,
)
from basho.agent.policy import ToolPolicy
from basho.agent.simulated_tools import build_simulated_registry
from basho.agent.tasks import RESEARCH_REPORT_PROFILE
from basho.audit import AuditDecision, InMemoryAuditLog
from basho.evidence.contracts import ArtifactStatus
from evidence_factories import PROJECT_A, TENANT_A
from maker_support import FixedVerifier, InMemoryEvidence, report_input
from report_factories import commit, report
from tool_support import github_fixtures

API = "https://featherless.test/v1"
KEY = "featherless-key-never-logged"
MODEL = "deepseek-ai/DeepSeek-V3.1"


def completion(message: dict[str, Any], finish: str) -> dict[str, Any]:
    return {
        "id": "req-1",
        "model": MODEL,
        "choices": [{"message": message, "finish_reason": finish}],
        "usage": {"prompt_tokens": 120, "completion_tokens": 30},
    }


class FakeFeatherless:
    def __init__(self, script: list[httpx.Response]) -> None:
        self.script = script
        self.requests: list[dict[str, Any]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(json.loads(request.content))
        assert request.headers["authorization"] == f"Bearer {KEY}"
        return self.script.pop(0)

    def client(self) -> OpenAICompatibleMessagesClient:
        return OpenAICompatibleMessagesClient(
            base_url=API,
            api_key=SecretStr(KEY),
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(self.handler)),
        )


# --- tradução -------------------------------------------------------------------------------


def test_history_translates_tool_use_and_tool_results() -> None:
    # Arrange: histórico no formato da Anthropic, como o Maker monta
    system = [{"type": "text", "text": "prompt", "cache_control": {"type": "ephemeral"}}]
    history: list[dict[str, Any]] = [
        {"role": "user", "content": "tarefa"},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "vou consultar"},
                {"type": "tool_use", "id": "c1", "name": "ledger_query_events", "input": {"a": 1}},
            ],
        },
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "c1", "content": '{"ok":1}'}],
        },
    ]

    # Act
    out = openai_messages(system, history)

    # Assert
    assert out[0] == {"role": "system", "content": "prompt"}
    assert out[1] == {"role": "user", "content": "tarefa"}
    assert out[2]["role"] == "assistant"
    assert out[2]["content"] == "vou consultar"
    assert out[2]["tool_calls"][0]["function"] == {
        "name": "ledger_query_events",
        "arguments": '{"a": 1}',
    }
    assert out[3] == {"role": "tool", "tool_call_id": "c1", "content": '{"ok":1}'}


@pytest.mark.parametrize(
    ("finish", "expected"),
    [("stop", "end_turn"), ("length", "max_tokens"), ("tool_calls", "end_turn")],
)
def test_stop_reason_mapping_without_tool_calls(finish: str, expected: str) -> None:
    response = parse_response(completion({"content": "{}"}, finish), MODEL)
    assert response.stop_reason == expected


def test_reasoning_is_stripped_and_invalid_arguments_stay_raw() -> None:
    # Arrange
    message = {
        "content": "<think>raciocínio interno</think>resposta",
        "tool_calls": [{"id": "x", "function": {"name": "t", "arguments": "{nao json"}}],
    }

    # Act
    response = parse_response(completion(message, "tool_calls"), MODEL)

    # Assert
    text, tool = response.content
    assert text.text == "resposta"  # type: ignore[union-attr]
    assert tool.input == "{nao json"  # type: ignore[union-attr]  # a policy nega e audita
    assert response.stop_reason == "tool_use"
    assert (response.usage.input_tokens, response.usage.output_tokens) == (120, 30)


@pytest.mark.parametrize(
    ("status", "retryable"), [(429, True), (503, True), (400, False), (401, False)]
)
async def test_http_errors_become_provider_errors_without_key(status: int, retryable: bool) -> None:
    fake = FakeFeatherless([httpx.Response(status, json={"error": {"message": "x"}})])
    with pytest.raises(MakerProviderError) as excinfo:
        await fake.client().messages.create(
            model=MODEL, max_tokens=100, system="s", tools=[], messages=[]
        )
    assert excinfo.value.run_error.code == "provider_status"
    assert excinfo.value.run_error.retryable is retryable
    assert KEY not in str(excinfo.value)


# --- Maker de ponta a ponta sobre o adaptador ------------------------------------------------


async def test_maker_runs_tool_loop_and_verifies_over_openai_compatible_api() -> None:
    # Arrange
    evidence = commit()
    draft = report(method_ids=(evidence.id,), result_ids=(evidence.id,))
    tool_turn = completion(
        {
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "github_list_commits", "arguments": "{}"},
                }
            ],
        },
        "tool_calls",
    )
    final_turn = completion({"content": draft.model_dump_json()}, "stop")
    fake = FakeFeatherless(
        [httpx.Response(200, json=tool_turn), httpx.Response(200, json=final_turn)]
    )
    registry = build_simulated_registry(github_fixtures())
    audit = InMemoryAuditLog()
    gateway = InMemoryEvidence([evidence])
    maker = Maker(
        client=fake.client(),
        registry=registry,
        policy=ToolPolicy(registry, audit, InMemoryApprovalStore()),
        checker=ReportDeterministicChecker(TENANT_A),
        verifier=FixedVerifier(),
        evidence=gateway,
        settings=ModelSettings(model=MODEL),
    )
    task = MakerTask(
        tenant_id=TENANT_A,
        run_id=uuid4(),
        project_id=PROJECT_A,
        profile=RESEARCH_REPORT_PROFILE,
        task_input=report_input(draft),
        is_synthetic=True,
    )

    # Act
    result = await maker.run(task)

    # Assert
    assert result.status is MakerStatus.COMPLETED
    assert result.outcome is not None and result.outcome.status is ArtifactStatus.VERIFIED
    assert [entry.decision for entry in audit.entries] == [AuditDecision.ALLOWED]
    first, second = fake.requests
    assert first["model"] == MODEL
    assert "thinking" not in first and "output_config" not in first
    assert {t["function"]["name"] for t in first["tools"]} >= {"github_list_commits"}
    assert second["messages"][-1]["role"] == "tool"
    assert second["messages"][-1]["tool_call_id"] == "call_1"
    assert all(call.model == MODEL for call in result.calls)


# --- escolha de provedor (worker) -----------------------------------------------------------


def _settings(**overrides: str) -> Any:
    from basho.config import Settings

    env = {
        "database_url": "postgresql+psycopg://x:y@localhost/x",
        "anthropic_api_key": "",
        "featherless_api_key": KEY,
        "featherless_base_url": API,
        "checker_model": "zai-org/GLM-4.6",
        "github_token": "",
        "tenant_id": "00000000-0000-0000-0000-000000000001",
        "maker_provider": "featherless",
        "maker_model": MODEL,
        **overrides,
    }
    return Settings.model_validate(env)


def test_featherless_provider_uses_openai_client_for_maker_and_checker() -> None:
    from basho.agent.checker import FallbackVerifier, OpenAICompatibleVerifier
    from basho.agent.worker import maker_and_verifier

    maker, checker = maker_and_verifier(_settings(), httpx.AsyncClient())
    assert isinstance(maker, OpenAICompatibleMessagesClient)
    assert isinstance(checker, OpenAICompatibleVerifier)
    assert checker.model_id == "zai-org/GLM-4.6"

    _, with_fallback = maker_and_verifier(
        _settings(checker_fallback_model="moonshotai/Kimi-K2-Instruct-0905"), httpx.AsyncClient()
    )
    assert isinstance(with_fallback, FallbackVerifier)


@pytest.mark.parametrize("field", ["checker_model", "checker_fallback_model"])
def test_checker_must_differ_from_maker(field: str) -> None:
    with pytest.raises(ValueError, match="diferentes"):
        _settings(**{field: MODEL})


# --- chave de fallback (segunda conta do Featherless) ---------------------------------------

FALLBACK_KEY = "fallback-key-never-logged"


class TwoAccounts:
    """Primária sem crédito (`status`), fallback ok. Grava qual chave cada chamada usou."""

    def __init__(self, status: int) -> None:
        self.status = status
        self.keys_used: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        key = request.headers["authorization"].removeprefix("Bearer ")
        self.keys_used.append(key)
        if key == KEY:
            return httpx.Response(self.status, json={"error": {"message": "sem crédito"}})
        return httpx.Response(200, json=completion({"content": "{}"}, "stop"))

    def client(self) -> OpenAICompatibleMessagesClient:
        return OpenAICompatibleMessagesClient(
            base_url=API,
            api_key=SecretStr(KEY),
            fallback_api_keys=[SecretStr(FALLBACK_KEY)],
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(self.handler)),
        )


async def _call(client: OpenAICompatibleMessagesClient) -> Any:
    return await client.messages.create(
        model=MODEL, max_tokens=10, system="s", tools=[], messages=[]
    )


@pytest.mark.parametrize("status", [401, 402, 403])
async def test_exhausted_primary_key_switches_to_fallback_and_stays(status: int) -> None:
    # Arrange
    accounts = TwoAccounts(status)
    client = accounts.client()

    # Act
    first = await _call(client)
    second = await _call(client)

    # Assert: tenta a primária uma vez, troca, e as chamadas seguintes já vão na fallback
    assert first.stop_reason == second.stop_reason == "end_turn"
    assert accounts.keys_used == [KEY, FALLBACK_KEY, FALLBACK_KEY]


async def test_rate_limit_does_not_switch_accounts() -> None:
    accounts = TwoAccounts(429)
    with pytest.raises(MakerProviderError) as excinfo:
        await _call(accounts.client())
    assert accounts.keys_used == [KEY]
    assert excinfo.value.run_error.retryable is True


async def test_both_keys_exhausted_fails_without_leaking_keys() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(402, json={"error": {"message": "sem crédito"}})

    client = OpenAICompatibleMessagesClient(
        base_url=API,
        api_key=SecretStr(KEY),
        fallback_api_keys=[SecretStr(FALLBACK_KEY)],
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(MakerProviderError) as excinfo:
        await _call(client)
    assert excinfo.value.run_error.retryable is False
    assert KEY not in str(excinfo.value) and FALLBACK_KEY not in str(excinfo.value)


async def test_checker_chain_falls_back_to_second_account() -> None:
    # Arrange: primária responde 402 no Checker; a segunda conta responde um veredito válido
    from basho.agent.worker import maker_and_verifier
    from report_factories import commit, report

    evidence = commit()
    draft = report(method_ids=(evidence.id,), result_ids=(evidence.id,))
    verdict = json.dumps({"verdict": "pass", "issues": [], "unsupported_claims": []})
    used: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        key = request.headers["authorization"].removeprefix("Bearer ")
        used.append(key)
        if key == KEY:
            return httpx.Response(402, json={})
        return httpx.Response(200, json=completion({"content": verdict}, "stop"))

    _, checker = maker_and_verifier(
        _settings(featherless_fallback_api_key=FALLBACK_KEY),
        httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    # Act
    result = await checker.verify(draft, [evidence])

    # Assert
    assert result.verdict.value == "pass"
    assert used == [KEY, FALLBACK_KEY]
