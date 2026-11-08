"""Relatório do dossiê → documento neutro (HTML para o Drive, blocos de texto para o Notion).

Regras que o texto gerado respeita (CLAUDE.md): toda afirmação traz suas fontes; lacunas e
divergências aparecem como pendência, nunca preenchidas; nada de horas, valores ou elegibilidade
inventados; linguagem "potencialmente qualificável, sujeito a análise". Texto vindo do GitHub
(mensagens de commit, títulos de PR) é **dado**: vai escapado no HTML e como texto puro no Notion.
"""

from __future__ import annotations

import html
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from basho.compliance.api_contracts import DossierEntryOut
from basho.evidence.contracts import EventKind, EvidenceEvent
from basho.publishing.clients.notion import rich_text

DISCLAIMER = (
    "O Basho apoia a análise: não decide enquadramento, não garante benefício fiscal e não "
    "submete o FORMP&D."
)
SECTION_ORDER = ("technological_challenge", "hypothesis", "method", "result", "uncertainty")
SECTION_LABELS = {
    "technological_challenge": "Desafio tecnológico",
    "hypothesis": "Hipótese",
    "method": "Método",
    "result": "Resultado",
    "uncertainty": "Incerteza",
}
OUTCOME_LABELS = {"positive": "positivo", "negative": "negativo", "inconclusive": "inconclusivo"}
MAX_LABEL_CHARS = 140

BlockKind = Literal["h2", "p", "bullet", "note"]


@dataclass(frozen=True, slots=True)
class Block:
    kind: BlockKind
    text: str


@dataclass(frozen=True, slots=True)
class RenderedDoc:
    title: str
    blocks: tuple[Block, ...]

    def to_html(self) -> str:
        parts: list[str] = []
        in_list = False
        for block in self.blocks:
            if block.kind != "bullet" and in_list:
                parts.append("</ul>")
                in_list = False
            text = html.escape(block.text)
            if block.kind == "bullet":
                if not in_list:
                    parts.append("<ul>")
                    in_list = True
                parts.append(f"<li>{text}</li>")
            elif block.kind == "h2":
                parts.append(f"<h2>{text}</h2>")
            elif block.kind == "note":
                parts.append(f"<p><i>{text}</i></p>")
            else:
                parts.append(f"<p>{text}</p>")
        if in_list:
            parts.append("</ul>")
        title = html.escape(self.title)
        return (
            f'<!doctype html><html><head><meta charset="utf-8"><title>{title}</title></head>'
            f"<body><h1>{title}</h1>{''.join(parts)}</body></html>"
        )

    def to_notion_blocks(self) -> list[dict[str, Any]]:
        kinds = {
            "h2": "heading_2",
            "p": "paragraph",
            "bullet": "bulleted_list_item",
            "note": "callout",
        }
        return [
            {
                "object": "block",
                "type": kinds[b.kind],
                kinds[b.kind]: {"rich_text": rich_text(b.text)},
            }
            for b in self.blocks
        ]


def _clip(text: str) -> str:
    one_line = " ".join(text.split())
    return one_line if len(one_line) <= MAX_LABEL_CHARS else one_line[: MAX_LABEL_CHARS - 1] + "…"


def evidence_label(event: EvidenceEvent) -> str:
    """Descrição curta e segura de uma evidência (texto externo vai só como dado)."""
    payload = event.payload
    if event.kind is EventKind.COMMIT_OBSERVED:
        sha = str(payload.get("sha") or event.source_ref)[:7]
        message = _clip(
            str(payload.get("message") or "").splitlines()[0] if payload.get("message") else ""
        )
        repo = f" ({payload['repo']})" if payload.get("repo") else ""
        return f"commit {sha}{repo}" + (f": {message}" if message else "")
    if event.kind is EventKind.PULL_REQUEST_OBSERVED:
        title = _clip(str(payload.get("title") or ""))
        return f"PR #{payload.get('number', '?')}" + (f": {title}" if title else "")
    return f"{event.kind.value} {event.source_ref}"


class _Sources:
    """Numera as fontes na ordem em que são citadas."""

    def __init__(self, events: Sequence[EvidenceEvent]) -> None:
        self._by_id: Mapping[str, EvidenceEvent] = {str(e.id): e for e in events}
        self._numbers: dict[str, int] = {}

    def cite(self, evidence_ids: Sequence[object]) -> str:
        marks: list[str] = []
        for raw in evidence_ids:
            key = str(raw)
            if key not in self._by_id:
                continue
            number = self._numbers.setdefault(key, len(self._numbers) + 1)
            marks.append(f"[{number}]")
        return " " + "".join(marks) if marks else ""

    def listing(self) -> list[Block]:
        ordered = sorted(self._numbers.items(), key=lambda item: item[1])
        return [Block("bullet", f"[{n}] {evidence_label(self._by_id[key])}") for key, n in ordered]


def _claims(draft: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    claims = draft.get("claims")
    return [c for c in claims if isinstance(c, dict)] if isinstance(claims, list) else []


def _str(value: object) -> str:
    return value if isinstance(value, str) else ""


def render_report(
    entry: DossierEntryOut,
    *,
    project_name: str,
    is_synthetic: bool,
    generated_at: datetime,
) -> RenderedDoc:
    draft: Mapping[str, Any] = entry.content
    sources = _Sources(entry.evidence)
    blocks: list[Block] = []

    header = (
        f"Projeto: {project_name} · estado do registro: {entry.status.value} · gerado pelo Basho "
        f"em {generated_at:%d/%m/%Y %H:%M} UTC a partir das evidências do projeto."
    )
    blocks.append(Block("p", header))
    if is_synthetic:
        blocks.append(Block("note", "Documento de demonstração: dados sintéticos."))
    summary = _str(draft.get("summary"))
    if summary:
        blocks += [Block("h2", "Resumo"), Block("p", summary)]

    claims = _claims(draft)
    supported = [c for c in claims if c.get("status", "supported") == "supported"]
    for section in SECTION_ORDER:
        rows = [c for c in supported if c.get("section") == section]
        if rows:
            blocks.append(Block("h2", SECTION_LABELS[section]))
            blocks += [
                Block(
                    "bullet", _str(c.get("text")) + sources.cite(list(c.get("evidence_ids") or []))
                )
                for c in rows
            ]

    experiments = draft.get("experiments")
    if isinstance(experiments, list) and experiments:
        blocks.append(Block("h2", "Desfechos dos experimentos"))
        for item in experiments:
            if isinstance(item, dict):
                outcome = OUTCOME_LABELS.get(_str(item.get("outcome")), "não classificado")
                blocks.append(
                    Block(
                        "bullet",
                        f"({outcome}) {_str(item.get('description'))}"
                        + sources.cite(list(item.get("evidence_ids") or [])),
                    )
                )

    disputed = [c for c in claims if c.get("status") == "disputed"]
    if disputed:
        blocks.append(Block("h2", "Pontos em disputa"))
        blocks += [
            Block(
                "bullet",
                f"{_str(c.get('text'))} — motivo: {_str(c.get('dispute_reason'))}"
                + sources.cite(list(c.get("evidence_ids") or [])),
            )
            for c in disputed
        ]

    pending = [
        f"{_str(c.get('question'))} (responsável: {_str(c.get('ask_role'))})"
        for c in claims
        if c.get("status") == "pending"
    ]
    missing = draft.get("missing")
    if isinstance(missing, list):
        pending += [
            f"{_str(m.get('question'))} (responsável: {_str(m.get('ask_role'))})"
            for m in missing
            if isinstance(m, dict)
        ]
    if pending:
        blocks.append(Block("h2", "Pendências para os responsáveis"))
        blocks += [Block("bullet", item) for item in pending]

    listing = sources.listing()
    if listing:
        blocks += [Block("h2", "Fontes"), *listing]

    eligibility = _str(draft.get("eligibility_note"))
    blocks.append(Block("h2", "Nota"))
    if eligibility:
        blocks.append(Block("p", eligibility))
    blocks.append(Block("note", DISCLAIMER))
    blocks.append(Block("p", f"Registro {entry.artifact_id}."))

    return RenderedDoc(title=document_title(entry.title, entry.artifact_id), blocks=tuple(blocks))


def document_title(title: str, artifact_id: UUID) -> str:
    """Título estável e único por artefato: reexecutar encontra o mesmo documento."""
    return f"Relatório BASHO — {_clip(title)} — {str(artifact_id)[:8]}"
