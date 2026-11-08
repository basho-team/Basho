"""Validação da saída do Maker e o retorno que ele recebe para refazer (ADR-0004, ADR-0009).

A saída é JSON validado pelo schema Pydantic do perfil. Além do schema, o código confere que
os campos de identificação (projeto, pesquisador, período...) são exatamente os da tarefa: o
modelo não escolhe sobre quem ou sobre quando está escrevendo.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from basho.agent.verifier import CheckIssue

MAX_FEEDBACK_ITEMS = 20
INVALID_JSON = "invalid_json"
SCHEMA_VIOLATION = "schema_violation"
TASK_FIELD_MISMATCH = "task_field_mismatch"
TRUNCATED = "truncated_output"
INVALID_CHARACTERS = "invalid_characters"
EXTRA_FIELD = "<campo extra>"

_FENCE = re.compile(r"^\s*```(?:json)?\s*\n?|\n?\s*```\s*$")


@dataclass(frozen=True, slots=True)
class OutputProblem:
    """Por que a saída foi rejeitada. `details` vira o retorno ao Maker (sem dado externo)."""

    code: str
    details: tuple[str, ...]


def _strip_fence(text: str) -> str:
    return _FENCE.sub("", text.strip())


def _location(loc: tuple[int | str, ...], error_type: str) -> str:
    """Caminho do erro. Em `extra_forbidden` o último segmento é uma chave escrita pelo modelo
    (pode carregar texto externo), então ele não volta no feedback."""
    parts = [str(part) for part in loc]
    if error_type == "extra_forbidden" and parts:
        parts[-1] = EXTRA_FIELD
    return ".".join(parts) or "<raiz>"


def _has_nul(value: object) -> bool:
    if isinstance(value, str):
        return "\x00" in value
    if isinstance(value, dict):
        return any(_has_nul(key) or _has_nul(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_has_nul(item) for item in value)
    return False


def parse_output(
    text: str, schema: type[BaseModel], expected: Mapping[str, Any]
) -> BaseModel | OutputProblem:
    """JSON → schema → campos da tarefa. Devolve o artefato ou o problema."""
    try:
        raw = json.loads(_strip_fence(text))
    except json.JSONDecodeError:
        return OutputProblem(INVALID_JSON, ("a resposta não é um único objeto JSON válido",))
    if _has_nul(raw):
        # O ledger rejeita U+0000; refazer custa menos que perder o run inteiro na gravação.
        return OutputProblem(INVALID_CHARACTERS, ("remova caracteres de controle nulos (U+0000)",))
    try:
        artifact = schema.model_validate(raw)
    except ValidationError as exc:
        details = tuple(
            f"{_location(error['loc'], error['type'])}: {error['type']}"
            for error in exc.errors(include_input=False, include_url=False)
        )
        return OutputProblem(SCHEMA_VIOLATION, details[:MAX_FEEDBACK_ITEMS])
    dumped = artifact.model_dump(mode="json")
    mismatched = tuple(
        f"{name}: use exatamente o valor informado na tarefa"
        for name, value in expected.items()
        if dumped.get(name) != value
    )
    if mismatched:
        return OutputProblem(TASK_FIELD_MISMATCH, mismatched)
    return artifact


def output_feedback(problem: OutputProblem) -> str:
    lines = "\n".join(f"- {detail}" for detail in problem.details)
    return (
        f"Sua resposta foi rejeitada pela validação ({problem.code}):\n{lines}\n"
        "Corrija e responda novamente somente com o objeto JSON completo no schema pedido."
    )


def checks_feedback(issues: Sequence[CheckIssue]) -> str:
    """Retorno dos checks determinísticos (#9). Mensagens são do nosso código, não externas."""
    lines = "\n".join(
        f"- {issue.code}: {issue.message}" for issue in list(issues)[:MAX_FEEDBACK_ITEMS]
    )
    return (
        "O rascunho não passou nos checks determinísticos:\n"
        f"{lines}\n"
        "Corrija só o que foi apontado, cite apenas IDs de evidência retornados pelas tools e "
        "responda novamente somente com o objeto JSON completo."
    )


def truncated_feedback() -> str:
    return (
        "Sua resposta foi cortada por limite de tamanho. Seja mais conciso e responda somente "
        "com o objeto JSON completo."
    )
