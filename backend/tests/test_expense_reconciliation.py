from datetime import date
from decimal import Decimal, localcontext
from itertools import permutations
from uuid import UUID

import pytest
from pydantic import ValidationError

from basho.expenses.service import Allocation, Expense, ReconciliationState, reconcile
from fiscal_factories import SCOPE, SOURCE, expense


def updated(item: Expense, **changes: object) -> Expense:
    return Expense.model_validate({**item.model_dump(), **changes})


def test_mixed_expense_proposal_preserves_residual_and_does_not_change_input() -> None:
    item = expense()
    result = reconcile(SCOPE, (item,))
    assert result.items[0].state == ReconciliationState.CONSISTENT
    assert result.items[0].proposed_amount == Decimal("60.00")
    assert result.items[0].unallocated_amount == Decimal("40.01")
    assert result.totals[0].consistent_proposed == Decimal("60.00")
    assert item.amount == Decimal("100.01")


def test_document_payment_and_posting_count_once_with_explicit_same_item() -> None:
    items = (expense(1), expense(2), expense(3))
    for ordering in permutations(items):
        result = reconcile(SCOPE, ordering)
        assert len(result.items) == 3
        assert result.items[0].state == ReconciliationState.CONSISTENT
        assert all(i.duplicate_of == UUID(int=1) for i in result.items[1:])
        assert result.totals[0].consistent_proposed == Decimal("60.00")
        assert result == reconcile(SCOPE, items)


def test_deduplication_does_not_guess_equivalence_without_key() -> None:
    items = tuple(updated(expense(n), economic_item_ref=None) for n in (1, 2))
    result = reconcile(SCOPE, items)
    assert all(i.state == ReconciliationState.PENDING for i in result.items)
    assert result.totals[0].consistent_proposed == 0
    assert result.totals[0].pending_known == Decimal("200.02")


def test_conflicting_amount_preserves_all_sources_without_choosing_total() -> None:
    other = updated(expense(2), amount=Decimal("110.01"))
    result = reconcile(SCOPE, (expense(), other))
    assert all(i.state == ReconciliationState.CONFLICT for i in result.items)
    assert result.totals[0].consistent_proposed == 0
    assert result.totals[0].pending_known == 0
    assert result.totals[0].pending_unknown_count == 1


def test_unknown_value_is_not_zero_and_stays_pending() -> None:
    result = reconcile(SCOPE, (updated(expense(), amount=None),))
    assert result.items[0].expense.amount is None
    assert result.items[0].state == ReconciliationState.PENDING
    assert result.totals[0].pending_unknown_count == 1


def test_explicit_exclusion_retains_reason_and_sources_without_including_total() -> None:
    result = reconcile(SCOPE, (updated(expense(), excluded_reason="Fora do recorte declarado"),))
    assert result.items[0].state == ReconciliationState.EXCLUDED
    assert result.items[0].expense.sources == (SOURCE,)
    assert result.items[0].expense.excluded_reason
    assert result.totals[0].consistent_proposed == 0


@pytest.mark.parametrize(
    "changes,gap",
    [
        ({"confirmed": False}, "human_confirmation_required"),
        ({"sources": ()}, "formal_source_required"),
        ({"attributable_limit": None}, "missing_attributable_limit"),
        ({"attributable_limit": Decimal("101.00")}, "attributable_limit_exceeds_document"),
        ({"period_start": date(2024, 12, 1)}, "period_requires_review"),
    ],
)
def test_material_gaps_block_proposed_total(changes: dict[str, object], gap: str) -> None:
    result = reconcile(SCOPE, (updated(expense(), **changes),))
    assert gap in result.items[0].gaps
    assert result.totals[0].consistent_proposed == 0


def test_allocation_cannot_exceed_document_or_attributable_limit() -> None:
    allocation = Allocation(
        activity_id=UUID(int=10),
        amount=Decimal("120.00"),
        basis="Proposta sintética incorreta",
        sources=(SOURCE,),
    )
    result = reconcile(SCOPE, (updated(expense(), allocations=(allocation,)),))
    assert set(result.items[0].gaps) >= {
        "allocation_exceeds_document",
        "allocation_exceeds_attributable_limit",
    }
    assert result.items[0].unallocated_amount is None
    assert result.totals[0].consistent_proposed == 0


def test_missing_allocation_evidence_blocks_even_with_nonempty_basis() -> None:
    allocation = Allocation(activity_id=UUID(int=10), amount=Decimal("60"), basis="Proposta")
    result = reconcile(SCOPE, (updated(expense(), allocations=(allocation,)),))
    assert "allocation_evidence_required" in result.items[0].gaps


@pytest.mark.parametrize(
    "amount",
    [Decimal("-1"), Decimal("NaN"), Decimal("Infinity"), Decimal("0.001"), Decimal("1e-100000")],
)
def test_invalid_money_is_rejected(amount: Decimal) -> None:
    with pytest.raises(ValidationError):
        updated(expense(), amount=amount)


def test_float_is_not_accepted_as_money() -> None:
    with pytest.raises(ValidationError):
        updated(expense(), amount=0.1)


def test_decimal_precision_is_independent_of_process_context() -> None:
    with localcontext() as context:
        context.prec = 2
        result = reconcile(SCOPE, (expense(),))
    assert result.items[0].unallocated_amount == Decimal("40.01")


def test_currencies_are_not_added_or_converted() -> None:
    other = updated(expense(2), currency="USD", economic_item_ref="synthetic:expense-2")
    result = reconcile(SCOPE, (expense(), other))
    assert [(t.currency, t.consistent_proposed) for t in result.totals] == [
        ("BRL", Decimal("60.00")),
        ("USD", Decimal("60.00")),
    ]


def test_wrong_tenant_or_project_in_source_fails_closed() -> None:
    source = SOURCE.model_copy(update={"tenant_id": UUID(int=99)})
    with pytest.raises(ValueError, match="tenant/projeto"):
        reconcile(SCOPE, (updated(expense(), sources=(source,)),))


def test_wrong_scope_or_repeated_ids_fail_closed() -> None:
    with pytest.raises(ValueError, match="IDs"):
        reconcile(SCOPE, (expense(), expense()))
    other_scope = SCOPE.model_copy(update={"project_id": UUID(int=99)})
    with pytest.raises(ValueError, match="escopo"):
        reconcile(SCOPE, (updated(expense(), scope=other_scope),))


def test_github_commit_cannot_confirm_a_formal_value() -> None:
    source = SOURCE.model_copy(update={"origin": "github"})
    result = reconcile(SCOPE, (updated(expense(), sources=(source,)),))
    assert "formal_source_required" in result.items[0].gaps


def test_tampered_model_copy_is_revalidated_at_service_boundary() -> None:
    with pytest.raises(ValidationError):
        reconcile(SCOPE, (expense().model_copy(update={"amount": Decimal("-1")}),))


def test_synthetic_and_real_inputs_are_not_combined() -> None:
    with pytest.raises(ValueError, match="sintéticos e reais"):
        reconcile(SCOPE, (expense(), updated(expense(2), is_synthetic=False)))
