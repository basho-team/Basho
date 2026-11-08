"""Texto legível da consolidação gerencial (Markdown determinístico).

Derivado de `ManagerConsolidation`; **não** substitui os IDs/estados estruturados (CONTRATOS.md
do handoff: "narrativas são derivadas"). Regras:
- todo item cita a origem: pesquisador, versão e ID curto do item; evidências por ID curto;
- itens de versões cujo texto o pesquisador ainda não aprovou são marcados como rascunho;
- resultados negativos e inconclusivos aparecem com o mesmo destaque que os positivos;
- horas só como referências a eventos formais (nunca soma); nota fiscal fixa ao final;
- texto vindo de relatórios/fontes é tratado como dado: caracteres de Markdown/HTML escapados.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from uuid import UUID

from basho.agent.artifacts import ExperimentOutcomeKind
from basho.reports.consolidation import (
    ConsolidatedClaim,
    ManagerConsolidation,
    ReportStatus,
    ReviewState,
    SourceRef,
)

SHORT_ID_LENGTH = 8
DRAFT_MARK = " _(rascunho: texto ainda não aprovado pelo pesquisador)_"
_MARKDOWN_SPECIAL = re.compile(r"([\\`*_{}\[\]<>()#+\-!|~])")

OUTCOME_LABELS: dict[ExperimentOutcomeKind, str] = {
    ExperimentOutcomeKind.POSITIVE: "Positivo",
    ExperimentOutcomeKind.NEGATIVE: "Negativo",
    ExperimentOutcomeKind.INCONCLUSIVE: "Inconclusivo",
}
STATE_LABELS: dict[ReviewState, str] = {
    ReviewState.TEXT_APPROVED: "texto aprovado",
    ReviewState.CHANGES_REQUESTED: "correções pedidas",
    ReviewState.AWAITING_REVIEW: "aguardando revisão",
}


def escape(text: str) -> str:
    """Escapa Markdown/HTML e achata quebras de linha: conteúdo de fonte é dado, não marcação."""
    flat = " ".join(text.split())
    return _MARKDOWN_SPECIAL.sub(r"\\\1", flat)


UNIQUE_IDS_SENTINEL = 32


def short(value: UUID, length: int = SHORT_ID_LENGTH) -> str:
    return value.hex[:length]


def unique_prefix_length(ids: Iterable[UUID], minimum: int = SHORT_ID_LENGTH) -> int:
    """Menor prefixo hex (≥ `minimum`) que distingue todos os IDs exibidos (sem ambiguidade)."""
    distinct = {i.hex for i in ids}
    for length in range(minimum, UNIQUE_IDS_SENTINEL + 1):
        if len({h[:length] for h in distinct}) == len(distinct):
            return length
    return UNIQUE_IDS_SENTINEL


def _rendered_ids(c: ManagerConsolidation) -> set[UUID]:
    ids: set[UUID] = {c.project_id, c.consolidation_id}
    for s in c.reports:
        ids.add(s.researcher_id)
        ids.update(s.formal_hours_event_ids)
    cited: list[tuple[SourceRef, tuple[UUID, ...]]] = [
        *((x.source, x.evidence_ids) for x in (*c.advances, *c.result_claims, *c.uncertainties)),
        *((r.source, r.evidence_ids) for r in c.results),
        *((d.source, d.evidence_ids) for d in c.disputes),
        *((q.source, q.evidence_ids) for q in c.open_questions),
    ]
    for source, evidence in cited:
        ids.update((source.item_id, source.researcher_id, *evidence))
    return ids


def render_manager_summary(
    consolidation: ManagerConsolidation,
    *,
    researcher_names: Mapping[UUID, str] | None = None,
) -> str:
    """Gera o resumo do período para o gerente. Mesma entrada ⇒ mesmo texto."""
    names = researcher_names or {}
    width = unique_prefix_length(_rendered_ids(consolidation))

    def sid(value: UUID) -> str:
        return short(value, width)

    def who(researcher_id: UUID) -> str:
        return escape(names.get(researcher_id, f"pesquisador {sid(researcher_id)}"))

    def cite(source: SourceRef, evidence: Iterable[UUID] = ()) -> str:
        refs = ", ".join(sid(e) for e in evidence)
        evidence_part = f"; evidências: {refs}" if refs else "; sem evidência citada"
        draft = "" if source.researcher_review_id else DRAFT_MARK
        return (
            f" — {who(source.researcher_id)}, v{source.version_number}, "
            f"item {sid(source.item_id)}{evidence_part}{draft}"
        )

    c = consolidation
    lines = [
        f"# Consolidação do período {c.period.start.isoformat()} a {c.period.end.isoformat()}",
        "",
        f"Projeto {sid(c.project_id)} · consolidação {sid(c.consolidation_id)} · "
        f"{len(c.reports)} relatório(s) · fuso {escape(c.period.timezone)}",
    ]
    if c.is_synthetic:
        lines.append("")
        lines.append("> Dados sintéticos de demonstração.")
    lines += _section("Situação das revisões", [_status_line(s, who) for s in c.reports])
    lines += _results(c, cite)
    lines += _claims("Avanços", c.advances, cite)
    lines += _claims("Afirmações de resultado", c.result_claims, cite)
    lines += _claims("Incertezas", c.uncertainties, cite)
    lines += _section(
        "Perguntas abertas",
        [
            f"- **{escape(q.ask_role)}** ({escape(q.topic)}): {escape(q.question)}"
            + cite(q.source, q.evidence_ids)
            for q in c.open_questions
        ],
    )
    lines += _section(
        "Conflitos entre evidências",
        [
            f"- {escape(d.text)} **Motivo:** {escape(d.reason)}" + cite(d.source, d.evidence_ids)
            for d in c.disputes
        ],
    )
    lines += _section("Horas: referências a registros formais", _hours_lines(c, who, sid))
    lines += ["", "---", "", f"_{c.note}_", ""]
    return "\n".join(lines)


def _section(title: str, items: list[str], empty: str = "- Nenhum item.") -> list[str]:
    return ["", f"## {title}", "", *(items or [empty])]


def _status_line(status: ReportStatus, who: Callable[[UUID], str]) -> str:
    line = (
        f"- {who(status.researcher_id)} — v{status.current_version_number}: "
        f"pesquisador {STATE_LABELS[status.researcher.state]}, "
        f"gerente {STATE_LABELS[status.manager.state]}"
    )
    if status.approval_outdated:
        line += (
            f" ⚠ aprovação do texto refere-se à v{status.approved_version_number}, "
            "não à versão atual"
        )
    return line


def _results(c: ManagerConsolidation, cite: Callable[..., str]) -> list[str]:
    counts = " · ".join(
        f"{OUTCOME_LABELS[kind]}: {c.outcome_counts.get(kind, 0)}" for kind in ExperimentOutcomeKind
    )
    lines = ["", "## Resultados de experimentos", "", counts, ""]
    if not c.results:
        return [*lines, "- Nenhum experimento registrado no período."]
    for kind in ExperimentOutcomeKind:
        for r in (r for r in c.results if r.outcome is kind):
            lines.append(
                f"- **{OUTCOME_LABELS[kind]}:** {escape(r.description)}"
                + cite(r.source, r.evidence_ids)
            )
    return lines


def _claims(
    title: str, claims: tuple[ConsolidatedClaim, ...], cite: Callable[..., str]
) -> list[str]:
    return _section(title, [f"- {escape(x.text)}" + cite(x.source, x.evidence_ids) for x in claims])


def _hours_lines(
    c: ManagerConsolidation, who: Callable[[UUID], str], sid: Callable[[UUID], str]
) -> list[str]:
    lines = []
    for s in c.reports:
        refs = ", ".join(sid(e) for e in s.formal_hours_event_ids)
        detail = f"eventos {refs}" if refs else "sem registro formal no período (lacuna)"
        lines.append(f"- {who(s.researcher_id)}: {detail}")
    lines.append("- Horas não são somadas nem inferidas nesta consolidação.")
    return lines
