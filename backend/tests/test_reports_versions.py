"""Versões imutáveis, correções rastreáveis e revisão por versão exata."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from basho.agent.artifacts import ClaimStatus, ExperimentOutcomeKind
from basho.reports.corrections import (
    AddExperiment,
    InvalidCorrectionError,
    ReportCorrection,
    ResolveMissing,
    ReviseClaim,
    ReviseExperimentOutcome,
    WithdrawClaim,
    apply_correction,
)
from basho.reports.versions import (
    InvalidHistoryError,
    ReportVersion,
    ReviewDecision,
    VersionConflictError,
    review_version,
    validate_history,
)
from reports_helpers import RESEARCHER_ANA, at, first_version

PR43 = UUID("aaaaaaaa-0000-4000-8000-000000000043")
NEW_EVIDENCE = UUID("eeeeeeee-0000-4000-8000-000000000301")
HOURS_EVENT = UUID("dddddddd-0000-4000-8000-000000000999")
PENDING_CLAIM = 3  # hipótese do SMOTE na fixture
NEGATIVE_EXPERIMENT = 1


def _correction(base: ReportVersion, *ops: object) -> ReportCorrection:
    return ReportCorrection.model_validate(
        {
            "base_version_id": base.id,
            "author_id": RESEARCHER_ANA,
            "author_role": "pesquisador",
            "reason": "Resposta à pendência sobre a hipótese do PR #43.",
            "operations": ops,
        }
    )


def _answer_hypothesis(base: ReportVersion) -> ReportVersion:
    op = ReviseClaim(
        claim_index=PENDING_CLAIM,
        text="Hipótese: rebalancear com SMOTE recupera a precisão perdida na classe rara.",
        status=ClaimStatus.SUPPORTED,
        evidence_ids=(PR43, NEW_EVIDENCE),
    )
    return apply_correction([base], _correction(base, op), new_version_id=uuid4(), created_at=at(5))


def test_correction_creates_new_version_and_keeps_previous_intact() -> None:
    # Arrange
    v1 = first_version()
    # Act
    v2 = _answer_hypothesis(v1)
    # Assert
    assert v2.number == 2
    assert v2.supersedes_id == v1.id
    assert v2.draft.claims[PENDING_CLAIM].status is ClaimStatus.SUPPORTED
    assert v1.draft.claims[PENDING_CLAIM].status is ClaimStatus.PENDING
    assert v2.change is not None
    assert v2.change.affected_claims == (PENDING_CLAIM,)
    assert v2.change.author_role == "pesquisador"
    assert v2.is_synthetic


def test_correction_on_outdated_version_is_conflict() -> None:
    # Arrange
    v1 = first_version()
    v2 = _answer_hypothesis(v1)
    stale = _correction(v1, WithdrawClaim(claim_index=0, reason="Afirmação duplicada no texto."))
    # Act / Assert
    with pytest.raises(VersionConflictError) as exc:
        apply_correction([v1, v2], stale, new_version_id=uuid4(), created_at=at(9))
    assert exc.value.current_id == v2.id


def test_review_of_old_version_is_conflict_and_does_not_approve_current() -> None:
    # Arrange
    v1 = first_version()
    v2 = _answer_hypothesis(v1)
    # Act / Assert
    with pytest.raises(VersionConflictError):
        review_version(
            [v1, v2],
            review_id=uuid4(),
            version_id=v1.id,
            reviewer_id=RESEARCHER_ANA,
            reviewer_role="pesquisador",
            decision=ReviewDecision.TEXT_APPROVED,
            reviewed_at=at(10),
        )


def test_answer_without_evidence_cannot_become_supported() -> None:
    # Arrange
    v1 = first_version()
    op = ReviseClaim(
        claim_index=PENDING_CLAIM,
        text="Hipótese informada verbalmente, ainda sem registro escrito.",
        status=ClaimStatus.SUPPORTED,
    )
    # Act / Assert
    with pytest.raises(InvalidCorrectionError):
        apply_correction([v1], _correction(v1, op), new_version_id=uuid4(), created_at=at(1))


def test_negative_outcome_change_requires_evidence_and_keeps_experiment() -> None:
    # Arrange
    v1 = first_version()
    op = ReviseExperimentOutcome(
        experiment_index=NEGATIVE_EXPERIMENT,
        outcome=ExperimentOutcomeKind.INCONCLUSIVE,
        evidence_ids=(NEW_EVIDENCE,),
        reason="Nova rodada indica que a queda depende da calibração.",
    )
    # Act
    v2 = apply_correction([v1], _correction(v1, op), new_version_id=uuid4(), created_at=at(2))
    # Assert
    assert len(v2.draft.experiments) == len(v1.draft.experiments)
    revised = v2.draft.experiments[NEGATIVE_EXPERIMENT]
    assert revised.outcome is ExperimentOutcomeKind.INCONCLUSIVE
    assert NEW_EVIDENCE in revised.evidence_ids
    assert v2.change is not None
    assert "negative → inconclusive" in v2.change.operations[0]
    with pytest.raises(ValidationError):
        ReviseExperimentOutcome(
            experiment_index=0,
            outcome=ExperimentOutcomeKind.POSITIVE,
            evidence_ids=(),
            reason="Sem evidência nova para a mudança.",
        )


def test_no_operation_removes_experiments() -> None:
    # Arrange
    with pytest.raises(ValidationError):
        ReportCorrection.model_validate(
            {
                "base_version_id": uuid4(),
                "author_id": RESEARCHER_ANA,
                "author_role": "pesquisador",
                "reason": "Remover experimento que deu errado.",
                "operations": [{"kind": "remove_experiment", "experiment_index": 1}],
            }
        )


def test_formal_hours_gap_only_closes_with_formal_event_reference() -> None:
    # Arrange
    v1 = first_version()
    by_text = ResolveMissing(missing_index=0, evidence_ids=(NEW_EVIDENCE,))
    by_event = ResolveMissing(missing_index=0, formal_hours_event_ids=(HOURS_EVENT,))
    # Act / Assert
    with pytest.raises(InvalidCorrectionError):
        apply_correction([v1], _correction(v1, by_text), new_version_id=uuid4(), created_at=at(3))
    v2 = apply_correction([v1], _correction(v1, by_event), new_version_id=uuid4(), created_at=at(3))
    assert v2.draft.formal_hours_event_ids == (HOURS_EVENT,)
    assert v2.draft.missing == ()


def test_multiple_operations_keep_original_indexes() -> None:
    # Arrange
    v1 = first_version()
    ops = (
        WithdrawClaim(claim_index=0, reason="Desafio repetido em outro relatório."),
        ReviseClaim(
            claim_index=PENDING_CLAIM,
            text="Hipótese do SMOTE ainda sem critério de sucesso definido pelo time.",
            status=ClaimStatus.PENDING,
            question="Qual métrica e limiar definem sucesso do rebalanceamento com SMOTE?",
            ask_role="pesquisador",
        ),
        AddExperiment(
            description="Rebalanceamento com SMOTE no dataset de vibração (primeira rodada).",
            outcome=ExperimentOutcomeKind.NEGATIVE,
            evidence_ids=(NEW_EVIDENCE,),
        ),
    )
    # Act
    v2 = apply_correction([v1], _correction(v1, *ops), new_version_id=uuid4(), created_at=at(4))
    # Assert
    assert len(v2.draft.claims) == len(v1.draft.claims) - 1
    assert v2.draft.claims[-1].question is not None
    assert v2.draft.experiments[-1].outcome is ExperimentOutcomeKind.NEGATIVE
    assert v2.change is not None
    assert v2.change.affected_claims == (0, PENDING_CLAIM)


def test_invalid_index_is_rejected() -> None:
    v1 = first_version()
    op = WithdrawClaim(claim_index=42, reason="Índice que não existe na versão.")
    with pytest.raises(InvalidCorrectionError):
        apply_correction([v1], _correction(v1, op), new_version_id=uuid4(), created_at=at(1))


def test_history_must_be_a_contiguous_chain() -> None:
    # Arrange
    v1 = first_version()
    v2 = _answer_hypothesis(v1)
    orphan = v2.model_copy(update={"supersedes_id": uuid4()})
    # Act / Assert
    assert validate_history([v2, v1]) == (v1, v2)
    with pytest.raises(InvalidHistoryError):
        validate_history([v1, orphan])
    with pytest.raises(InvalidHistoryError):
        validate_history([v2])


def test_version_lineage_invariants() -> None:
    v1 = first_version()
    with pytest.raises(ValidationError):
        ReportVersion(
            id=uuid4(), tenant_id=v1.tenant_id, number=2, draft=v1.draft, created_at=at(1)
        )
