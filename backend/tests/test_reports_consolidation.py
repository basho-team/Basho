"""Consolidação gerencial: versão atual, revisado vs. pendente, negativos preservados, origem."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from basho.agent.artifacts import ClaimStatus, ExperimentOutcomeKind
from basho.reports.consolidation import (
    CONSOLIDATION_NOTE,
    InconsistentConsolidationError,
    ReportInput,
    ReviewState,
    consolidate,
)
from basho.reports.corrections import ReportCorrection, ReviseClaim, apply_correction
from basho.reports.versions import (
    ReportReview,
    ReportVersion,
    ReviewDecision,
    ReviewerNotAllowedError,
    ReviewerRole,
    review_version,
)
from reports_helpers import MANAGER, RESEARCHER_ANA, at, first_version

SECOND = "reports/second_researcher_draft.json"
PR43 = UUID("aaaaaaaa-0000-4000-8000-000000000043")


def _approve(history: list[ReportVersion], version: ReportVersion, minute: int) -> ReportReview:
    return review_version(
        history,
        review_id=uuid4(),
        version_id=version.id,
        reviewer_id=version.key.researcher_id,
        reviewer_role=ReviewerRole.RESEARCHER,
        decision=ReviewDecision.TEXT_APPROVED,
        reviewed_at=at(minute),
    )


def _answer(v1: ReportVersion) -> ReportVersion:
    correction = ReportCorrection(
        base_version_id=v1.id,
        author_id=RESEARCHER_ANA,
        author_role="pesquisador",
        reason="Hipótese registrada no PR #43 após pedido do gerente.",
        operations=(
            ReviseClaim(
                claim_id=v1.claim_ids[3],
                text="Hipótese: SMOTE recupera a precisão na classe rara de vibração.",
                status=ClaimStatus.SUPPORTED,
                evidence_ids=(PR43,),
            ),
        ),
    )
    return apply_correction([v1], correction, new_version_id=uuid4(), created_at=at(20))


def test_consolidation_keeps_negative_and_inconclusive_results_with_source() -> None:
    # Arrange
    ana, bia = first_version(), first_version(SECOND)
    # Act
    result = consolidate([ReportInput(versions=(ana,)), ReportInput(versions=(bia,))])
    # Assert
    counts = result.outcome_counts
    assert counts[ExperimentOutcomeKind.POSITIVE] == 1
    assert counts[ExperimentOutcomeKind.NEGATIVE] == 1
    assert counts[ExperimentOutcomeKind.INCONCLUSIVE] == 1
    negative = next(r for r in result.results if r.outcome is ExperimentOutcomeKind.NEGATIVE)
    assert negative.source.version_id == ana.id
    assert negative.source.item_id == ana.experiment_ids[1]
    assert result.tenant_id == ana.tenant_id
    assert result.period == ana.draft.period
    assert result.is_synthetic
    assert result.note == CONSOLIDATION_NOTE


def test_consolidation_separates_text_approved_from_pending_review() -> None:
    # Arrange
    ana, bia = first_version(), first_version(SECOND)
    review = _approve([bia], bia, 1)
    # Act
    result = consolidate(
        [ReportInput(versions=(ana,)), ReportInput(versions=(bia,), reviews=(review,))]
    )
    # Assert
    states = {s.researcher_id: s.researcher.state for s in result.reports}
    assert states[ana.key.researcher_id] is ReviewState.AWAITING_REVIEW
    assert states[bia.key.researcher_id] is ReviewState.TEXT_APPROVED
    assert not result.all_text_approved
    assert all(
        r.source.researcher_review_id is None
        for r in result.results
        if r.source.version_id == ana.id
    )
    assert all(
        r.source.researcher_review_id == review.id
        for r in result.results
        if r.source.version_id == bia.id
    )


def test_approval_of_old_version_does_not_carry_to_correction() -> None:
    # Arrange
    v1 = first_version()
    approval_v1 = _approve([v1], v1, 1)
    v2 = _answer(v1)
    # Act
    result = consolidate([ReportInput(versions=(v1, v2), reviews=(approval_v1,))])
    # Assert
    status = result.reports[0]
    assert status.current_version_number == 2
    assert status.researcher.state is ReviewState.AWAITING_REVIEW
    assert status.approved_version_number == 1
    assert status.approval_outdated
    assert all(item.source.version_number == 2 for item in result.advances)


def test_open_questions_and_disputes_are_listed_for_manager() -> None:
    # Arrange
    ana, bia = first_version(), first_version(SECOND)
    # Act
    result = consolidate([ReportInput(versions=(ana,)), ReportInput(versions=(bia,))])
    # Assert
    topics = {q.topic for q in result.open_questions}
    assert topics == {"hypothesis", "formal_hours"}
    assert len(result.disputes) == 1
    assert result.disputes[0].source.researcher_id == bia.key.researcher_id


def test_formal_hours_are_references_never_sums() -> None:
    ana, bia = first_version(), first_version(SECOND)
    result = consolidate([ReportInput(versions=(ana,)), ReportInput(versions=(bia,))])
    by_researcher = {s.researcher_id: s.formal_hours_event_ids for s in result.reports}
    assert by_researcher[ana.key.researcher_id] == ()
    assert len(by_researcher[bia.key.researcher_id]) == 1
    assert "hours" not in type(result).model_fields


def test_rejects_mixed_scope_duplicates_and_orphan_reviews() -> None:
    # Arrange
    ana = first_version()
    other_project = ana.model_copy(
        update={"draft": ana.draft.model_copy(update={"project_id": uuid4()}), "id": uuid4()}
    )
    orphan = _approve([ana], ana, 1).model_copy(update={"version_id": uuid4()})
    # Act / Assert
    with pytest.raises(InconsistentConsolidationError):
        consolidate([ReportInput(versions=(ana,)), ReportInput(versions=(other_project,))])
    with pytest.raises(InconsistentConsolidationError):
        consolidate([ReportInput(versions=(ana,)), ReportInput(versions=(first_version(),))])
    with pytest.raises(InconsistentConsolidationError):
        consolidate([ReportInput(versions=(ana,), reviews=(orphan,))])
    with pytest.raises(InconsistentConsolidationError):
        consolidate([])


def test_latest_review_of_same_role_wins() -> None:
    v1 = first_version()
    approved = _approve([v1], v1, 1)
    changes = approved.model_copy(
        update={"id": uuid4(), "decision": ReviewDecision.CHANGES_REQUESTED, "reviewed_at": at(2)}
    )
    result = consolidate([ReportInput(versions=(v1,), reviews=(changes, approved))])
    assert result.reports[0].researcher.state is ReviewState.CHANGES_REQUESTED
    assert result.reports[0].researcher.review_id == changes.id
    assert result.reports[0].manager.state is ReviewState.AWAITING_REVIEW


def test_only_the_author_can_review_as_researcher() -> None:
    v1 = first_version()
    with pytest.raises(ReviewerNotAllowedError):
        review_version(
            [v1],
            review_id=uuid4(),
            version_id=v1.id,
            reviewer_id=MANAGER,
            reviewer_role=ReviewerRole.RESEARCHER,
            decision=ReviewDecision.TEXT_APPROVED,
            reviewed_at=at(1),
        )


def test_manager_approval_alone_does_not_mark_text_approved() -> None:
    v1 = first_version()
    manager_ok = review_version(
        [v1],
        review_id=uuid4(),
        version_id=v1.id,
        reviewer_id=MANAGER,
        reviewer_role=ReviewerRole.MANAGER,
        decision=ReviewDecision.TEXT_APPROVED,
        reviewed_at=at(1),
    )
    result = consolidate([ReportInput(versions=(v1,), reviews=(manager_ok,))])
    assert not result.all_text_approved
    assert all(r.source.researcher_review_id is None for r in result.results)


def test_consolidation_id_changes_when_inputs_change() -> None:
    v1 = first_version()
    before = consolidate([ReportInput(versions=(v1,))])
    after = consolidate([ReportInput(versions=(v1,), reviews=(_approve([v1], v1, 1),))])
    assert before.consolidation_id != after.consolidation_id
    assert after.input_version_ids == (v1.id,)
