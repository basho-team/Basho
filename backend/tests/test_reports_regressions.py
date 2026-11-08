"""Reproduz os defeitos do #43 (versão aabfaaf): posição como referência, lacuna só em texto,
revisão do gerente apagando a do pesquisador."""

from __future__ import annotations

from uuid import UUID, uuid4

from basho.agent.artifacts import ClaimStatus
from basho.reports.consolidation import ReportInput, ReviewState, consolidate
from basho.reports.corrections import (
    CorrectionOp,
    ReportCorrection,
    ResolveMissing,
    ReviseClaim,
    WithdrawClaim,
    apply_correction,
)
from basho.reports.versions import (
    ReportVersion,
    ReviewDecision,
    ReviewerRole,
    create_first_version,
    review_version,
)
from reports_helpers import MANAGER, RESEARCHER_ANA, at, first_version

PR43 = UUID("aaaaaaaa-0000-4000-8000-000000000043")
HOURS = UUID("dddddddd-0000-4000-8000-000000000999")


def _correct(base: ReportVersion, *ops: CorrectionOp) -> ReportVersion:
    c = ReportCorrection(
        base_version_id=base.id,
        author_id=RESEARCHER_ANA,
        author_role="pesquisador",
        reason="Correção sintética para teste de regressão.",
        operations=ops,
    )
    return apply_correction([base], c, new_version_id=uuid4(), created_at=at(5))


def test_item_ids_survive_withdrawal_that_shifts_positions() -> None:
    v1 = first_version()
    hypothesis_id = v1.claim_ids[3]
    v2 = _correct(v1, WithdrawClaim(claim_id=v1.claim_ids[0], reason="Desafio duplicado."))
    # a hipótese mudou de posição (3 → 2), mas mantém o mesmo ID
    assert v2.claim_ids.index(hypothesis_id) == 2
    assert v2.change is not None
    assert v2.change.withdrawn_claim_ids == (v1.claim_ids[0],)
    assert v1.claim_ids[0] not in v2.claim_ids
    assert len(v1.claim_ids) == len(v1.draft.claims)  # versão antiga preserva seus IDs
    result = consolidate([ReportInput(versions=(v1, v2))])
    q = next(q for q in result.open_questions if q.topic == "hypothesis")
    assert q.source.item_id == hypothesis_id


def test_item_ids_are_deterministic_and_not_created_by_consolidation() -> None:
    v1 = first_version()
    again = create_first_version(
        version_id=v1.id,
        tenant_id=v1.tenant_id,
        draft=v1.draft,
        created_at=at(0),
        is_synthetic=True,
    )
    assert again.claim_ids == v1.claim_ids
    assert again.experiment_ids == v1.experiment_ids
    assert again.missing_ids == v1.missing_ids
    first = consolidate([ReportInput(versions=(v1,))])
    second = consolidate([ReportInput(versions=(again,))])
    assert first.consolidation_id == second.consolidation_id
    assert {r.source.item_id for r in first.results} <= set(v1.experiment_ids)


def test_resolved_gap_is_structured_not_only_text() -> None:
    v1 = first_version()
    gap_id = v1.missing_ids[0]
    v2 = _correct(v1, ResolveMissing(missing_id=gap_id, formal_hours_event_ids=(HOURS,)))
    assert v2.change is not None
    (gap,) = v2.change.resolved_gaps
    assert gap.missing_id == gap_id
    assert gap.field == "formal_hours"
    assert gap.formal_hours_event_ids == (HOURS,)
    assert gap_id not in v2.missing_ids


def test_manager_review_does_not_erase_researcher_approval() -> None:
    v1 = first_version()
    approve = review_version(
        [v1],
        review_id=uuid4(),
        version_id=v1.id,
        reviewer_id=RESEARCHER_ANA,
        reviewer_role=ReviewerRole.RESEARCHER,
        decision=ReviewDecision.TEXT_APPROVED,
        reviewed_at=at(1),
    )
    manager = review_version(
        [v1],
        review_id=uuid4(),
        version_id=v1.id,
        reviewer_id=MANAGER,
        reviewer_role=ReviewerRole.MANAGER,
        decision=ReviewDecision.CHANGES_REQUESTED,
        reviewed_at=at(2),
    )
    status = consolidate([ReportInput(versions=(v1,), reviews=(approve, manager))]).reports[0]
    assert status.researcher.state is ReviewState.TEXT_APPROVED
    assert status.researcher.review_id == approve.id
    assert status.manager.state is ReviewState.CHANGES_REQUESTED
    assert status.manager.review_id == manager.id


def test_revised_claim_keeps_its_id() -> None:
    v1 = first_version()
    cid = v1.claim_ids[3]
    v2 = _correct(
        v1,
        ReviseClaim(
            claim_id=cid,
            text="Hipótese: SMOTE recupera a classe rara de vibração.",
            status=ClaimStatus.SUPPORTED,
            evidence_ids=(PR43,),
        ),
    )
    assert v2.claim_ids == v1.claim_ids
    assert v2.change is not None and v2.change.affected_claim_ids == (cid,)


def test_same_instant_reviews_resolve_deterministically_regardless_of_input_order() -> None:
    # Apontado pelo Codex: ordenar só por reviewed_at dependia da ordem de entrada.
    v1 = first_version()
    a = review_version(
        [v1],
        review_id=UUID(int=1),
        version_id=v1.id,
        reviewer_id=RESEARCHER_ANA,
        reviewer_role=ReviewerRole.RESEARCHER,
        decision=ReviewDecision.TEXT_APPROVED,
        reviewed_at=at(1),
    )
    b = a.model_copy(update={"id": UUID(int=2), "decision": ReviewDecision.CHANGES_REQUESTED})
    one = consolidate([ReportInput(versions=(v1,), reviews=(a, b))]).reports[0].researcher
    two = consolidate([ReportInput(versions=(v1,), reviews=(b, a))]).reports[0].researcher
    assert one == two
    assert one.review_id == b.id
