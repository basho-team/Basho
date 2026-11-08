from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from basho.compliance.service import Criterion, Signal, prepare_findings
from basho.expenses.service import reconcile
from fiscal_factories import SCOPE, criterion, expense

TODAY = date(2026, 11, 7)


def test_consistent_allocation_requires_human_fiscal_judgment() -> None:
    findings = prepare_findings(reconcile(SCOPE, (expense(),)), criterion(), assessed_on=TODAY)
    finding = findings[0]
    assert finding.signal == Signal.FISCAL_JUDGMENT_REQUIRED
    assert finding.sources and finding.criterion.references
    assert finding.justification and finding.next_step
    assert "não comprova" in finding.justification
    assert finding.gaps == ()
    assert finding.assessed_on == TODAY
    assert "approved" not in finding.model_dump()


def test_missing_source_produces_gap_not_fabricated_citation() -> None:
    item = expense().model_copy(update={"sources": (), "allocations": ()})
    finding = prepare_findings(reconcile(SCOPE, (item,)), criterion(), assessed_on=TODAY)[0]
    assert finding.signal == Signal.INSUFFICIENT_INFORMATION
    assert finding.sources == ()
    assert "missing_evidence" in finding.gaps


def test_conflict_and_duplicates_stay_visible_with_sources() -> None:
    inputs = (expense(), expense(2))
    findings = prepare_findings(reconcile(SCOPE, inputs), criterion(), assessed_on=TODAY)
    assert findings[1].signal == Signal.POSSIBLE_INCOMPATIBILITY
    assert findings[1].sources
    conflicting = expense(2).model_copy(update={"amount": Decimal("200")})
    findings = prepare_findings(
        reconcile(SCOPE, (expense(), conflicting)), criterion(), assessed_on=TODAY
    )
    assert all(f.signal == Signal.POSSIBLE_INCOMPATIBILITY for f in findings)


@pytest.mark.parametrize(
    "change,expected_gap",
    [
        ({"applicable_years": (2024,)}, "criterion_not_verified_for_fiscal_year"),
        ({"valid_from": date(2025, 2, 1)}, "criterion_does_not_cover_full_fiscal_year"),
        ({"kind": "legal_reference"}, "specialist_interpretation_required"),
    ],
)
def test_criterion_period_and_specialist_interpretation_are_explicit(
    change: dict[str, object], expected_gap: str
) -> None:
    rule = Criterion.model_validate({**criterion().model_dump(), **change})
    finding = prepare_findings(reconcile(SCOPE, (expense(),)), rule, assessed_on=TODAY)[0]
    assert finding.signal == Signal.INSUFFICIENT_INFORMATION
    assert expected_gap in finding.gaps


def test_source_check_date_after_assessment_does_not_establish_applicability() -> None:
    finding = prepare_findings(
        reconcile(SCOPE, (expense(),)), criterion(), assessed_on=date(2026, 11, 6)
    )[0]
    assert "criterion_reference_checked_after_assessment" in finding.gaps


def test_criterion_without_reference_or_version_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Criterion.model_validate({**criterion().model_dump(), "references": ()})
    with pytest.raises(ValidationError):
        Criterion.model_validate({**criterion().model_dump(), "version": " "})


def test_assessment_recomputes_tampered_reconciliation_state() -> None:
    result = reconcile(SCOPE, (expense().model_copy(update={"confirmed": False}),))
    item = result.items[0].model_copy(update={"state": "consistent", "gaps": ()})
    result = result.model_copy(update={"items": (item,)})
    finding = prepare_findings(result, criterion(), assessed_on=TODAY)[0]
    assert finding.signal == Signal.INSUFFICIENT_INFORMATION
    assert "human_confirmation_required" in finding.gaps
