"""Peças puras do worker (#10, #23, #25): custo estimado, backoff, ponte de config e migração."""

import importlib.util
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from basho.agent.costs import estimate_cost_usd
from basho.agent.llm import CallRecord
from basho.agent.runs import RunStatus
from basho.agent.tasks import TaskKind
from basho.agent.worker import (
    BACKOFF_MAX_SECONDS,
    model_settings_from,
    retry_delay,
)
from basho.config import Settings
from basho.evidence.contracts import ArtifactStatus
from conftest import VALID_ENV

MIGRATION = Path(__file__).resolve().parents[1] / "migrations" / "versions" / "0006_agent_runs.py"


def _call(model: str, **tokens: int) -> CallRecord:
    fields: dict[str, Any] = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    } | tokens
    return CallRecord(
        model=model, prompt_version="v2", stop_reason="end_turn", latency_ms=10, **fields
    )


def test_cost_uses_list_prices_for_each_token_kind() -> None:
    # Arrange: 1M de cada tipo no Opus 5.5 = 4 + 20 + 0,20 + 5 (escrita = 1,25 x entrada)
    call = _call(
        "claude-opus-5-5",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        cache_read_input_tokens=1_000_000,
        cache_creation_input_tokens=1_000_000,
    )

    # Act / Assert
    assert estimate_cost_usd(call) == Decimal("29.200000")


def test_cost_of_a_typical_call_is_rounded_to_micro_dollars() -> None:
    # Arrange
    call = _call(
        "claude-opus-5-5", input_tokens=1200, output_tokens=300, cache_read_input_tokens=900
    )

    # Act / Assert: 1200*4 + 300*20 + 900*0,2 = 10980 / 1e6
    assert estimate_cost_usd(call) == Decimal("0.010980")


def test_unknown_model_has_no_invented_price() -> None:
    assert estimate_cost_usd(_call("modelo-desconhecido", input_tokens=10)) is None


@pytest.mark.parametrize(
    ("attempts", "seconds"), [(1, 5), (2, 10), (3, 20), (20, BACKOFF_MAX_SECONDS)]
)
def test_retry_delay_is_exponential_and_capped(attempts: int, seconds: int) -> None:
    assert retry_delay(attempts) == timedelta(seconds=seconds)


def test_model_settings_come_from_environment_settings() -> None:
    # Arrange
    env = {name.lower(): value for name, value in VALID_ENV.items()}
    settings = Settings.model_validate(env | {"maker_model": "claude-x", "maker_effort": "low"})

    # Act
    model = model_settings_from(settings)

    # Assert
    assert (model.model, model.effort) == ("claude-x", "low")


def test_migration_check_values_match_enums() -> None:
    # Arrange
    spec = importlib.util.spec_from_file_location("migration_0006", MIGRATION)
    assert spec is not None
    assert spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    # Assert
    assert set(migration._RUN_STATUSES) == {value.value for value in RunStatus}
    assert set(migration._TASK_KINDS) == {value.value for value in TaskKind}
    # Só os estados que `verify_artifact` produz (o artefato do Maker nunca vira formal aqui)
    assert set(migration._ARTIFACT_STATUSES) <= {value.value for value in ArtifactStatus}
