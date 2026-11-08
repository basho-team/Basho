"""Registro de tools do agente (ADR-0005).

O registro é montado na inicialização e falha rápido: tool sem nível, com nível `formal`,
duplicada ou com nível diferente do contrato (`MVP_TOOLS`) não entra.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from pydantic import ValidationError

from basho.agent.tasks import TaskProfile
from basho.agent.tools import AGENT_ALLOWED_LEVELS, MVP_TOOLS, PermissionLevel, Tool, ToolSpec


class ToolRegistrationError(ValueError):
    """Tool recusada pelo registro (erro de inicialização)."""


def _validated_spec(tool: object) -> ToolSpec:
    """Revalida a spec: `ToolSpec.model_construct` sem `level` não passa por aqui."""
    spec = getattr(tool, "spec", None)
    if not isinstance(spec, ToolSpec):
        raise ToolRegistrationError("tool sem ToolSpec")
    fields = {name: getattr(spec, name) for name in ToolSpec.model_fields if hasattr(spec, name)}
    try:
        return ToolSpec.model_validate(fields)
    except ValidationError as exc:
        missing = sorted({str(error["loc"][0]) for error in exc.errors() if error["loc"]})
        msg = f"ToolSpec inválida (campos: {missing})"
        raise ToolRegistrationError(msg) from None


@dataclass(frozen=True, slots=True)
class RegisteredTool:
    """Tool + a spec **validada e congelada no registro**.

    A policy usa sempre esta `spec`, nunca `tool.spec` lido na hora da chamada: trocar o
    atributo depois do registro não muda o nível nem a exigência de aprovação.
    """

    spec: ToolSpec
    tool: Tool


class ToolRegistry:
    """Tools disponíveis ao agente, indexadas por nome. Nunca contém tools `formal`."""

    def __init__(
        self,
        tools: Iterable[Tool] = (),
        *,
        contract: Mapping[str, PermissionLevel] = MVP_TOOLS,
    ) -> None:
        self._contract = contract
        self._tools: dict[str, RegisteredTool] = {}
        for tool in tools:
            self.register(tool)

    def register(self, tool: Tool) -> None:
        spec = _validated_spec(tool)
        if spec.level not in AGENT_ALLOWED_LEVELS:
            msg = f"tool {spec.name!r} de nível {spec.level.value} não pode ser dada ao agente"
            raise ToolRegistrationError(msg)
        if spec.name in self._tools:
            msg = f"tool {spec.name!r} já registrada"
            raise ToolRegistrationError(msg)
        expected = self._contract.get(spec.name)
        if expected is not None and expected is not spec.level:
            msg = f"tool {spec.name!r} declara {spec.level.value}, contrato exige {expected.value}"
            raise ToolRegistrationError(msg)
        self._tools[spec.name] = RegisteredTool(spec=spec, tool=tool)

    def get(self, name: str) -> RegisteredTool | None:
        return self._tools.get(name)

    def levels(self) -> Mapping[str, PermissionLevel]:
        """Nome → nível, no formato aceito por `validate_allowlist`."""
        return MappingProxyType({name: entry.spec.level for name, entry in self._tools.items()})

    def specs_for(self, profile: TaskProfile) -> tuple[ToolSpec, ...]:
        """Specs expostas ao Maker para `profile`: allowlist ∩ registro ∩ níveis permitidos."""
        return tuple(
            entry.spec
            for name, entry in sorted(self._tools.items())
            if name in profile.allowed_tools and entry.spec.level in AGENT_ALLOWED_LEVELS
        )
