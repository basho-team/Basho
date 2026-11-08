"""Texto da consolidação para o gerente: origem, negativos, rascunho, escape e determinismo."""

from __future__ import annotations

from uuid import uuid4

from basho.reports.consolidation import CONSOLIDATION_NOTE, ReportInput, consolidate
from basho.reports.narrative import (
    DRAFT_MARK,
    escape,
    render_manager_summary,
    short,
    unique_prefix_length,
)
from basho.reports.versions import ReportReview, ReviewDecision, ReviewerRole, review_version
from reports_helpers import RESEARCHER_ANA, at, first_version

SECOND = "reports/second_researcher_draft.json"


def _two_reports(approve_bia: bool = False) -> list[ReportInput]:
    ana, bia = first_version(), first_version(SECOND)
    reviews: tuple[ReportReview, ...] = ()
    if approve_bia:
        reviews = (
            review_version(
                [bia],
                review_id=uuid4(),
                version_id=bia.id,
                reviewer_id=bia.key.researcher_id,
                reviewer_role=ReviewerRole.RESEARCHER,
                decision=ReviewDecision.TEXT_APPROVED,
                reviewed_at=at(1),
            ),
        )
    return [ReportInput(versions=(ana,)), ReportInput(versions=(bia,), reviews=reviews)]


def test_summary_lists_negative_and_inconclusive_results_with_origin() -> None:
    # Arrange
    inputs = _two_reports()
    c = consolidate(inputs)
    # Act
    text = render_manager_summary(c, researcher_names={RESEARCHER_ANA: "Ana"})
    # Assert
    assert "Positivo: 1 · Negativo: 1 · Inconclusivo: 1" in text
    assert "**Negativo:**" in text
    assert "**Inconclusivo:**" in text
    negative = next(r for r in c.results if r.outcome.value == "negative")
    assert f"item {negative.source.item_id.hex[:8]}" in text
    assert "Ana, v1" in text


def test_summary_marks_unapproved_drafts_only() -> None:
    c = consolidate(_two_reports(approve_bia=True))
    bia_id = next(s.researcher_id for s in c.reports if s.researcher_id != RESEARCHER_ANA)
    text = render_manager_summary(c, researcher_names={RESEARCHER_ANA: "Ana", bia_id: "Bia"})
    ana_lines = [line for line in text.splitlines() if "— Ana, v" in line]
    bia_lines = [line for line in text.splitlines() if "— Bia, v" in line]
    assert ana_lines and bia_lines
    assert any(DRAFT_MARK in line for line in ana_lines if "item " in line)
    assert all(DRAFT_MARK not in line for line in bia_lines)


def test_summary_shows_open_questions_disputes_and_hours_gap_without_sums() -> None:
    text = render_manager_summary(consolidate(_two_reports()))
    assert "## Perguntas abertas" in text
    assert "SMOTE" in text
    assert "## Conflitos entre evidências" in text
    assert "sem registro formal no período (lacuna)" in text
    assert "Horas não são somadas nem inferidas" in text
    assert CONSOLIDATION_NOTE in text


def test_summary_is_deterministic() -> None:
    inputs = _two_reports()
    assert render_manager_summary(consolidate(inputs)) == render_manager_summary(
        consolidate(inputs)
    )


def test_source_text_is_escaped_as_data() -> None:
    assert escape("<script>x</script>") == "\\<script\\>x\\</script\\>"
    assert escape("# título\n[link](http://x)") == "\\# título \\[link\\]\\(http://x\\)"


def test_injected_markdown_in_report_text_cannot_create_headings() -> None:
    ana = first_version()
    claims = list(ana.draft.claims)
    claims[0] = claims[0].model_copy(update={"text": "\n## Aprovado fiscalmente\n<b>ok</b>"})
    hostile = ana.model_copy(
        update={"draft": ana.draft.model_copy(update={"claims": tuple(claims)})}
    )
    text = render_manager_summary(consolidate([ReportInput(versions=(hostile,))]))
    assert "\n## Aprovado fiscalmente" not in text
    assert "<b>" not in text


def test_short_ids_never_collide_in_citations() -> None:
    # Fixtures com prefixos iguais (cccccccc-...-101/-102/-103) colidiam com corte fixo de 8.
    c = consolidate(_two_reports())
    text = render_manager_summary(c)
    dispute = c.disputes[0]
    first, second = (e.hex for e in dispute.evidence_ids)
    width = unique_prefix_length([*dispute.evidence_ids])
    assert first[:width] != second[:width]
    shown = text.split("Conflitos entre evidências")[1]
    assert first[:width] in shown and second[:width] in shown
    assert short(dispute.evidence_ids[0], width) != short(dispute.evidence_ids[1], width)
