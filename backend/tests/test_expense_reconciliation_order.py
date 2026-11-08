"""Regressão: ordem das alocações não pode transformar duplicata explícita em conflito."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

from basho.expenses.domain.models import Allocation, Expense, Scope, SourceRef
from basho.expenses.domain.reconciliation import reconcile

SCOPE = Scope(tenant_id=uuid4(), project_id=uuid4(), fiscal_year=2026)
ACTIVITY = uuid4()


def _source(reference: str) -> SourceRef:
    return SourceRef(
        tenant_id=SCOPE.tenant_id,
        project_id=SCOPE.project_id,
        reference=reference,
        revision="1",
        locator="p1",
        origin="formal_system",
    )


def _expense(amounts: list[str], reference: str) -> Expense:
    return Expense(
        id=uuid4(),
        scope=SCOPE,
        economic_item_ref="NF-1",
        period_start=date(2026, 3, 1),
        period_end=date(2026, 3, 1),
        currency="BRL",
        amount=Decimal("30.00"),
        attributable_limit=Decimal("30.00"),
        allocations=tuple(
            Allocation(
                activity_id=ACTIVITY, amount=Decimal(a), basis="b", sources=(_source(reference),)
            )
            for a in amounts
        ),
        sources=(_source(reference),),
        confirmed=True,
        is_synthetic=True,
    )


def test_same_allocations_in_different_order_are_duplicate_not_conflict() -> None:
    result = reconcile(
        SCOPE, (_expense(["10.00", "20.00"], "nota"), _expense(["20.00", "10.00"], "pagamento"))
    )
    states = sorted(item.state.value for item in result.items)
    assert states == ["consistent", "duplicate"]
