"""Somente dados sintéticos; nenhuma fonte ou decisão fiscal real."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from basho.compliance.service import Criterion, CriterionReference
from basho.expenses.service import Allocation, Expense, Scope, SourceRef

SCOPE = Scope(tenant_id=UUID(int=1), project_id=UUID(int=2), fiscal_year=2025)
SOURCE = SourceRef(
    tenant_id=SCOPE.tenant_id,
    project_id=SCOPE.project_id,
    reference="synthetic:document-1",
    revision="v1",
    locator="item 1",
    origin="user",
)


def expense(number: int = 1) -> Expense:
    return Expense(
        id=UUID(int=number),
        scope=SCOPE,
        economic_item_ref="synthetic:expense-1",
        period_start=date(2025, 1, 1),
        period_end=date(2025, 1, 31),
        currency="BRL",
        amount=Decimal("100.01"),
        attributable_limit=Decimal("60.00"),
        confirmed=True,
        sources=(SOURCE,),
        allocations=(
            Allocation(
                activity_id=UUID(int=10),
                amount=Decimal("60.00"),
                basis="Rateio declarado pelo responsável sintético",
                sources=(SOURCE,),
            ),
        ),
        is_synthetic=True,
    )


def criterion() -> Criterion:
    return Criterion(
        code="reconciliation-data-quality",
        title="Conciliação limitada",
        version="test-v1",
        kind="product_policy",
        applicable_years=(2025,),
        valid_from=date(2025, 1, 1),
        valid_until=date(2025, 12, 31),
        references=(
            CriterionReference(
                reference="synthetic:policy",
                version="test-v1",
                locator="section 1",
                checked_on=date(2026, 11, 7),
            ),
        ),
    )
