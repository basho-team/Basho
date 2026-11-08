"""Perfis de tarefa do Maker (ADR-0009, proposta; leitura literal da ADR-0004).

Um perfil não é um novo agente: é prompt versionado + allowlist de tools + schema de saída.
A allowlist é validada em código contra o registro de tools e `AGENT_ALLOWED_LEVELS`
(ADR-0005); nenhum perfil pode receber tool `formal` ou desconhecida.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, model_validator

from basho.agent.artifacts import ResearchReportDraft
from basho.agent.tools import AGENT_ALLOWED_LEVELS, MVP_TOOLS, PermissionLevel

PROMPTS_DIR = Path(__file__).parent / "prompts"
PROMPT_VERSION_PATTERN = r"^v\d+$"
TOOL_REGISTRY_CONTEXT_KEY = "tool_registry"
"""Chave do `context` de validação para trocar o registro de tools (testes, novos registros)."""


class TaskKind(StrEnum):
    RESEARCH_REPORT = "research_report"
    COORDINATION = "coordination"
    TECHNICAL_FISCAL = "technical_fiscal"
    INVESTIGATION = "investigation"


class ToolNotAllowedError(ValueError):
    """Allowlist de perfil com tool desconhecida ou de nível não permitido ao agente."""


class ProfileNotAvailableError(LookupError):
    """`TaskKind` declarado, mas sem perfil executável nesta entrega."""


def validate_allowlist(
    tools: Iterable[str], registry: Mapping[str, PermissionLevel]
) -> frozenset[str]:
    """Valida a allowlist contra `registry`; devolve-a como `frozenset`.

    Falha se alguma tool não estiver registrada ou tiver nível fora de `AGENT_ALLOWED_LEVELS`
    (em particular, `formal`).
    """
    allowlist = frozenset(tools)
    unknown = sorted(name for name in allowlist if name not in registry)
    if unknown:
        msg = f"tools desconhecidas na allowlist: {unknown}"
        raise ToolNotAllowedError(msg)
    forbidden = sorted(name for name in allowlist if registry[name] not in AGENT_ALLOWED_LEVELS)
    if forbidden:
        msg = f"tools com nível não permitido ao agente: {forbidden}"
        raise ToolNotAllowedError(msg)
    return allowlist


class TaskProfile(BaseModel):
    """Perfil de tarefa: `kind`, versão do prompt, allowlist de tools e schema de saída."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: TaskKind
    prompt_version: str = Field(pattern=PROMPT_VERSION_PATTERN)
    allowed_tools: frozenset[str] = Field(min_length=1)
    output_schema: type[BaseModel]

    @model_validator(mode="after")
    def _allowlist_respects_policy(self, info: ValidationInfo) -> Self:
        context: Any = info.context
        registry: Mapping[str, PermissionLevel] = MVP_TOOLS
        if isinstance(context, Mapping) and TOOL_REGISTRY_CONTEXT_KEY in context:
            registry = context[TOOL_REGISTRY_CONTEXT_KEY]
        validate_allowlist(self.allowed_tools, registry)
        return self

    @property
    def prompt_path(self) -> Path:
        return prompt_path(self.kind, self.prompt_version)


def prompt_path(kind: TaskKind, version: str) -> Path:
    """Caminho do prompt versionado: `prompts/<kind>/<version>.md`."""
    return PROMPTS_DIR / kind.value / f"{version}.md"


def load_prompt(profile: TaskProfile) -> str:
    """Lê o prompt de sistema do perfil (texto fixo; conteúdo variável vem depois)."""
    return profile.prompt_path.read_text(encoding="utf-8")


_RESEARCH_REPORT_WRITE_TOOLS = ("ledger_record_draft", "pending_item_open")

RESEARCH_REPORT_PROFILE = TaskProfile(
    kind=TaskKind.RESEARCH_REPORT,
    prompt_version="v1",
    allowed_tools=frozenset(
        {name for name, level in MVP_TOOLS.items() if level is PermissionLevel.READ}
        | set(_RESEARCH_REPORT_WRITE_TOOLS)
    ),
    output_schema=ResearchReportDraft,
)
"""Único perfil executável na primeira entrega. Sem tools `external` (nada sai do Basho)."""

TASK_PROFILES: Mapping[TaskKind, TaskProfile] = MappingProxyType(
    {TaskKind.RESEARCH_REPORT: RESEARCH_REPORT_PROFILE}
)


def get_profile(kind: TaskKind) -> TaskProfile:
    """Devolve o perfil executável de `kind` ou falha se ainda não houver um.

    A allowlist é revalidada a cada consulta (defesa em profundidade). Ainda assim, a policy
    (#6) deve checar o nível de cada tool a cada chamada, sem confiar só no perfil (ADR-0005).
    """
    try:
        profile = TASK_PROFILES[kind]
    except KeyError as exc:
        msg = f"tarefa {kind.value!r} declarada, mas sem perfil executável nesta entrega"
        raise ProfileNotAvailableError(msg) from exc
    validate_allowlist(profile.allowed_tools, MVP_TOOLS)
    return profile
