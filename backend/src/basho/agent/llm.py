"""Chamada ao Claude do Maker: parâmetros da API, registro por chamada e erros (ADR-0004).

Fronteira com o SDK `anthropic` (2.x, sobre `httpx2`). Regras da API para `claude-opus-5-5`:
sem `temperature`/`top_p`/`top_k` (400), `thinking` só `adaptive`, `tool_choice` só `auto`.
O prompt de sistema e as tools vão com `cache_control` (prefixo estável → cache).
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import anthropic
from pydantic import BaseModel, ConfigDict, Field

from basho.agent.runs import RunError
from basho.agent.tools import ToolSpec
from basho.logging import get_logger

DEFAULT_MAKER_MODEL = "claude-opus-5-5"
DEFAULT_MAKER_EFFORT = "high"
MAKER_MAX_TOKENS = 16000
"""Sem streaming: 16k mantém a resposta abaixo dos timeouts HTTP do SDK."""

PROVIDER_TIMEOUT = "provider_timeout"
PROVIDER_CONNECTION = "provider_connection"
PROVIDER_STATUS = "provider_status"
_RETRYABLE_STATUS_FLOOR = 500
_RATE_LIMITED = 429

_log = get_logger(__name__)


class MakerProviderError(RuntimeError):
    """Falha ao falar com o provedor. `run_error` vai para o `AgentRun` (#10 decide o retry)."""

    def __init__(self, run_error: RunError) -> None:
        super().__init__(run_error.message)
        self.run_error = run_error


class CallRecord(BaseModel):
    """Uma chamada ao modelo: o que entra em tracing/custo (#23). Sem conteúdo de prompt."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    model: str
    prompt_version: str
    stop_reason: str | None
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cache_read_input_tokens: int = Field(ge=0)
    cache_creation_input_tokens: int = Field(ge=0)
    latency_ms: int = Field(ge=0)
    request_id: str | None = None


class MessagesClient(Protocol):
    """O suficiente de `anthropic.AsyncAnthropic` para o Maker (facilita o mock)."""

    @property
    def messages(self) -> Any: ...


@dataclass(frozen=True, slots=True)
class ModelSettings:
    model: str = DEFAULT_MAKER_MODEL
    effort: str = DEFAULT_MAKER_EFFORT
    max_tokens: int = MAKER_MAX_TOKENS


def tool_definitions(specs: Sequence[ToolSpec]) -> list[dict[str, Any]]:
    """Tools no formato da API, em ordem estável; `cache_control` na última (cacheia todas)."""
    tools: list[dict[str, Any]] = [
        {"name": spec.name, "description": spec.description, "input_schema": spec.input_schema}
        for spec in sorted(specs, key=lambda item: item.name)
    ]
    if tools:
        tools[-1] = {**tools[-1], "cache_control": {"type": "ephemeral"}}
    return tools


def system_blocks(prompt: str) -> list[dict[str, Any]]:
    return [{"type": "text", "text": prompt, "cache_control": {"type": "ephemeral"}}]


def _usage(response: Any, name: str) -> int:
    value = getattr(response.usage, name, None)
    return value if isinstance(value, int) else 0


async def create_message(
    client: MessagesClient,
    settings: ModelSettings,
    *,
    prompt_version: str,
    system: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    messages: list[dict[str, Any]],
) -> tuple[Any, CallRecord]:
    """Uma chamada `messages.create`. Erros do provedor viram `MakerProviderError`."""
    started = time.monotonic()
    try:
        response = await client.messages.create(
            model=settings.model,
            max_tokens=settings.max_tokens,
            thinking={"type": "adaptive"},
            output_config={"effort": settings.effort},
            system=system,
            tools=tools,
            messages=messages,
        )
    except anthropic.APITimeoutError:
        raise MakerProviderError(_run_error(PROVIDER_TIMEOUT, "timeout no Claude", True)) from None
    except anthropic.APIConnectionError:
        message = "falha de conexão com o Claude"
        raise MakerProviderError(_run_error(PROVIDER_CONNECTION, message, True)) from None
    except anthropic.APIStatusError as exc:
        retryable = exc.status_code >= _RETRYABLE_STATUS_FLOOR or exc.status_code == _RATE_LIMITED
        message = f"Claude respondeu HTTP {exc.status_code}"
        raise MakerProviderError(_run_error(PROVIDER_STATUS, message, retryable)) from None
    record = CallRecord(
        model=str(getattr(response, "model", settings.model)),
        prompt_version=prompt_version,
        stop_reason=getattr(response, "stop_reason", None),
        input_tokens=_usage(response, "input_tokens"),
        output_tokens=_usage(response, "output_tokens"),
        cache_read_input_tokens=_usage(response, "cache_read_input_tokens"),
        cache_creation_input_tokens=_usage(response, "cache_creation_input_tokens"),
        latency_ms=int((time.monotonic() - started) * 1000),
        request_id=getattr(response, "_request_id", None),
    )
    _log.info("maker_call", **record.model_dump())
    return response, record


def _run_error(code: str, message: str, retryable: bool) -> RunError:
    return RunError(code=code, message=message, retryable=retryable)
