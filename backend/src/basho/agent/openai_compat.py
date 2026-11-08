"""Maker via API compatível com OpenAI (Featherless; ADR-0011).

`OpenAICompatibleMessagesClient` imita o pedaço de `anthropic.AsyncAnthropic` que o Maker usa
(`client.messages.create`): recebe os parâmetros no formato da Anthropic, chama
`/chat/completions` com tool calling e devolve um objeto com `content` (blocos `text` /
`tool_use`), `stop_reason`, `usage` e `model`. O loop do Maker, a policy e o audit não mudam.

Tradução:
- `system` (blocos) → mensagem `system`; `tools[].input_schema` → `tools[].function.parameters`.
- Bloco `tool_use` do assistente → `tool_calls`; `tool_result` do usuário → mensagem `tool`.
- `finish_reason`: `tool_calls` → `tool_use`, `length` → `max_tokens`, o resto → `end_turn`.
- `thinking`, `output_config` e `cache_control` são da Anthropic e ficam de fora. Raciocínio em
  `<think>...</think>` é removido do texto (o Checker nunca deve ver raciocínio do Maker).

Chave de fallback (`FEATHERLESS_FALLBACK_API_KEY`): se a chave em uso responder 401/402/403
(sem crédito, inválida), o cliente passa para a próxima e repete a chamada na hora.

Erros viram `MakerProviderError` com os mesmos códigos do Claude (`provider_timeout`,
`provider_connection`, `provider_status`); 429 e 5xx são retryable.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx
from pydantic import SecretStr

from basho.agent.llm import (
    PROVIDER_CONNECTION,
    PROVIDER_STATUS,
    PROVIDER_TIMEOUT,
    MakerProviderError,
)
from basho.agent.runs import RunError
from basho.logging import get_logger

DEFAULT_TIMEOUT_SECONDS = 180.0
_RATE_LIMITED = 429
_CLIENT_ERROR_FLOOR = 400
KEY_EXHAUSTED_STATUS = frozenset({401, 402, 403})
"""Chave sem crédito, inválida ou sem permissão: vale tentar a chave de fallback. 429 não
entra (é limite de concorrência, resolvido com retry, não com outra conta)."""
_SERVER_ERROR_FLOOR = 500
_THINK = re.compile(r"<think>.*?</think>", re.S)
_log = get_logger(__name__)
_STOP_REASONS = {"tool_calls": "tool_use", "function_call": "tool_use", "length": "max_tokens"}


@dataclass(frozen=True, slots=True)
class TextBlock:
    text: str
    type: str = "text"


@dataclass(frozen=True, slots=True)
class ToolUseBlock:
    id: str
    name: str
    input: object
    """Objeto JSON decodificado; argumentos inválidos chegam como string e a policy nega."""
    type: str = "tool_use"


@dataclass(frozen=True, slots=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


@dataclass(frozen=True, slots=True)
class Response:
    content: list[TextBlock | ToolUseBlock]
    stop_reason: str
    model: str
    usage: Usage = field(default_factory=Usage)
    _request_id: str | None = None


def _get(block: object, name: str) -> Any:
    return block.get(name) if isinstance(block, Mapping) else getattr(block, name, None)


def _system_text(system: object) -> str:
    if isinstance(system, str):
        return system
    if isinstance(system, Sequence):
        return "\n\n".join(str(_get(b, "text") or "") for b in system)
    return ""


def openai_tools(tools: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {"type": "object"}),
            },
        }
        for tool in tools
    ]


def openai_messages(system: object, messages: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Histórico no formato Anthropic → formato OpenAI."""
    out: list[dict[str, Any]] = []
    text = _system_text(system)
    if text:
        out.append({"role": "system", "content": text})
    for message in messages:
        role, content = message["role"], message["content"]
        if isinstance(content, str):
            out.append({"role": role, "content": content})
            continue
        texts = [str(_get(b, "text")) for b in content if _get(b, "type") == "text"]
        if role == "assistant":
            calls = [
                {
                    "id": str(_get(b, "id")),
                    "type": "function",
                    "function": {
                        "name": str(_get(b, "name")),
                        "arguments": json.dumps(_get(b, "input"), ensure_ascii=False),
                    },
                }
                for b in content
                if _get(b, "type") == "tool_use"
            ]
            entry: dict[str, Any] = {"role": "assistant", "content": "".join(texts) or None}
            if calls:
                entry["tool_calls"] = calls
            out.append(entry)
            continue
        for block in content:
            if _get(block, "type") == "tool_result":
                out.append(
                    {
                        "role": "tool",
                        "tool_call_id": str(_get(block, "tool_use_id")),
                        "content": str(_get(block, "content")),
                    }
                )
        if texts:
            out.append({"role": role, "content": "".join(texts)})
    return out


def parse_response(data: Mapping[str, Any], requested_model: str) -> Response:
    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    blocks: list[TextBlock | ToolUseBlock] = []
    text = _THINK.sub("", message.get("content") or "").strip()
    if text:
        blocks.append(TextBlock(text))
    for index, call in enumerate(message.get("tool_calls") or []):
        function = call.get("function") or {}
        raw = function.get("arguments") or "{}"
        try:
            arguments: object = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError:
            arguments = raw
        blocks.append(
            ToolUseBlock(
                id=str(call.get("id") or f"call_{index}"),
                name=str(function.get("name") or ""),
                input=arguments,
            )
        )
    has_tool = any(isinstance(b, ToolUseBlock) for b in blocks)
    finish = choice.get("finish_reason")
    stop = "tool_use" if has_tool else _STOP_REASONS.get(str(finish), "end_turn")
    if stop == "tool_use" and not has_tool:
        stop = "end_turn"
    usage = data.get("usage") or {}
    return Response(
        content=blocks,
        stop_reason=stop,
        model=str(data.get("model") or requested_model),
        usage=Usage(
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
        ),
        _request_id=data.get("id") if isinstance(data.get("id"), str) else None,
    )


class _Messages:
    def __init__(self, owner: OpenAICompatibleMessagesClient) -> None:
        self._owner = owner

    async def create(self, **kwargs: Any) -> Response:
        return await self._owner.create(**kwargs)


class OpenAICompatibleMessagesClient:
    """`MessagesClient` do Maker sobre `/chat/completions` (Featherless por padrão)."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: SecretStr,
        http_client: httpx.AsyncClient,
        fallback_api_keys: Sequence[SecretStr] = (),
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        temperature: float = 0.0,
    ) -> None:
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._keys = [api_key, *(k for k in fallback_api_keys if k.get_secret_value())]
        self._key_index = 0
        self._http = http_client
        self._timeout = timeout
        self._temperature = temperature
        self.messages = _Messages(self)

    async def create(
        self,
        *,
        model: str,
        max_tokens: int,
        system: object,
        tools: Sequence[Mapping[str, Any]],
        messages: Sequence[Mapping[str, Any]],
        **_anthropic_only: Any,
    ) -> Response:
        body: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": self._temperature,
            "messages": openai_messages(system, messages),
        }
        if tools:
            body["tools"] = openai_tools(tools)
        while True:
            response = await self._post(body)
            if response.status_code in KEY_EXHAUSTED_STATUS and self._next_key():
                continue
            break
        return self._parse(response, model)

    def _next_key(self) -> bool:
        """Sem crédito ou chave recusada: passa para a próxima chave (fica nela até reiniciar)."""
        if self._key_index + 1 >= len(self._keys):
            return False
        self._key_index += 1
        _log.warning("provider_key_switched", key_index=self._key_index)
        return True

    async def _post(self, body: dict[str, Any]) -> httpx.Response:
        key = self._keys[self._key_index].get_secret_value()
        try:
            return await self._http.post(
                self._url,
                json=body,
                headers={"Authorization": f"Bearer {key}"},
                timeout=self._timeout,
            )
        except httpx.TimeoutException:
            raise MakerProviderError(
                _error(PROVIDER_TIMEOUT, "timeout no provedor", True)
            ) from None
        except httpx.HTTPError:
            message = "falha de conexão com o provedor"
            raise MakerProviderError(_error(PROVIDER_CONNECTION, message, True)) from None

    def _parse(self, response: httpx.Response, model: str) -> Response:
        status = response.status_code
        if status >= 400:
            retryable = status >= _SERVER_ERROR_FLOOR or status == _RATE_LIMITED
            message = f"provedor respondeu HTTP {status}"
            raise MakerProviderError(_error(PROVIDER_STATUS, message, retryable))
        try:
            data = response.json()
        except ValueError:
            message = "resposta do provedor não é JSON"
            raise MakerProviderError(_error(PROVIDER_STATUS, message, True)) from None
        if not isinstance(data, dict):
            raise MakerProviderError(_error(PROVIDER_STATUS, "resposta inesperada", True))
        return parse_response(data, model)


def _error(code: str, message: str, retryable: bool) -> RunError:
    return RunError(code=code, message=message, retryable=retryable)
