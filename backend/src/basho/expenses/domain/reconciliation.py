"""Deduplicação explícita e aritmética exata; nunca decide elegibilidade fiscal."""

from collections import defaultdict
from uuid import UUID

from basho.expenses.domain.models import (
    CurrencyTotal,
    Expense,
    ReconciledItem,
    Reconciliation,
    ReconciliationState,
    Scope,
    cents,
    money,
)


def _scope_check(scope: Scope, expenses: tuple[Expense, ...]) -> None:
    if len({item.id for item in expenses}) != len(expenses):
        raise ValueError("IDs de despesa repetidos")
    if len({item.is_synthetic for item in expenses}) > 1:
        raise ValueError("Dados sintéticos e reais não podem ser conciliados juntos")
    for item in expenses:
        if item.scope != scope:
            raise ValueError("Despesa fora do escopo solicitado")
        sources = (*item.sources, *(s for a in item.allocations for s in a.sources))
        if any((s.tenant_id, s.project_id) != (scope.tenant_id, scope.project_id) for s in sources):
            raise ValueError("Referência fora do tenant/projeto solicitado")


def _gaps(item: Expense) -> tuple[str, ...]:
    gaps: list[str] = []
    if item.economic_item_ref is None:
        gaps.append("missing_economic_item_ref")
    if item.amount is None:
        gaps.append("missing_amount")
    if not item.confirmed:
        gaps.append("human_confirmation_required")
    if not item.sources or not any(s.origin in {"user", "formal_system"} for s in item.sources):
        gaps.append("formal_source_required")
    if (
        item.period_start.year != item.scope.fiscal_year
        or item.period_end.year != item.scope.fiscal_year
    ):
        gaps.append("period_requires_review")
    if item.attributable_limit is None:
        gaps.append("missing_attributable_limit")
    if not item.allocations:
        gaps.append("missing_allocation")
    if any(not allocation.sources for allocation in item.allocations):
        gaps.append("allocation_evidence_required")
    proposed = sum(cents(a.amount) for a in item.allocations)
    if item.amount is not None and proposed > cents(item.amount):
        gaps.append("allocation_exceeds_document")
    if item.attributable_limit is not None:
        if proposed > cents(item.attributable_limit):
            gaps.append("allocation_exceeds_attributable_limit")
        if item.amount is not None and item.attributable_limit > item.amount:
            gaps.append("attributable_limit_exceeds_document")
    return tuple(gaps)


def _signature(item: Expense) -> tuple[object, ...]:
    # Diferença de fontes é esperada em nota/pagamento/lançamento; divergência material não é.
    allocations = tuple(
        sorted(
            ((a.activity_id, a.amount, a.basis) for a in item.allocations), key=lambda a: str(a[0])
        )
    )
    return (
        item.currency,
        item.amount,
        item.attributable_limit,
        item.period_start,
        item.period_end,
        allocations,
        item.confirmed,
        item.excluded_reason,
    )


def _group(items: list[Expense]) -> list[ReconciledItem]:
    canonical = items[0]
    if len({_signature(item) for item in items}) > 1:
        return [
            ReconciledItem(
                expense=i, state=ReconciliationState.CONFLICT, gaps=("conflicting_economic_item",)
            )
            for i in items
        ]
    gaps = tuple(dict.fromkeys(gap for item in items for gap in _gaps(item)))
    state = ReconciliationState.PENDING if gaps else ReconciliationState.CONSISTENT
    if canonical.excluded_reason is not None:
        state = ReconciliationState.EXCLUDED
    proposed = money(sum(cents(a.amount) for a in canonical.allocations))
    residual = None
    if canonical.amount is not None and proposed <= canonical.amount:
        residual = money(cents(canonical.amount) - cents(proposed))
    first = ReconciledItem(
        expense=canonical,
        state=state,
        gaps=gaps,
        proposed_amount=proposed if state == ReconciliationState.CONSISTENT else None,
        unallocated_amount=residual,
    )
    return [
        first,
        *(
            ReconciledItem(
                expense=i,
                state=ReconciliationState.DUPLICATE,
                gaps=("explicit_duplicate",),
                duplicate_of=canonical.id,
            )
            for i in items[1:]
        ),
    ]


def _totals(items: tuple[ReconciledItem, ...]) -> tuple[CurrencyTotal, ...]:
    currencies = sorted({item.expense.currency for item in items})
    totals: list[CurrencyTotal] = []
    for currency in currencies:
        relevant = [item for item in items if item.expense.currency == currency]
        pending: dict[str | UUID, Expense] = {}
        for item in relevant:
            if item.state in {ReconciliationState.PENDING, ReconciliationState.CONFLICT}:
                pending[item.expense.economic_item_ref or item.expense.id] = item.expense
        # Conflitos não têm valor canônico confiável: conte como desconhecido, nunca escolha um.
        conflicts = {
            i.expense.economic_item_ref or i.expense.id
            for i in relevant
            if i.state == ReconciliationState.CONFLICT
        }
        known = [i for key, i in pending.items() if key not in conflicts and i.amount is not None]
        totals.append(
            CurrencyTotal(
                currency=currency,
                consistent_proposed=money(
                    sum(cents(i.proposed_amount) for i in relevant if i.proposed_amount is not None)
                ),
                pending_known=money(sum(cents(i.amount) for i in known if i.amount is not None)),
                pending_unknown_count=sum(
                    i.amount is None or key in conflicts for key, i in pending.items()
                ),
            )
        )
    return tuple(totals)


def reconcile(scope: Scope, expenses: tuple[Expense, ...]) -> Reconciliation:
    """Resultado imutável e independente da ordem de entrada; nenhuma entrada é descartada."""
    scope = Scope.model_validate(scope.model_dump())
    expenses = tuple(Expense.model_validate(item.model_dump()) for item in expenses)
    _scope_check(scope, expenses)
    groups: dict[str | UUID, list[Expense]] = defaultdict(list)
    for item in sorted(expenses, key=lambda item: str(item.id)):
        groups[item.economic_item_ref or item.id].append(item)
    items = tuple(
        sorted(
            (row for group in groups.values() for row in _group(group)),
            key=lambda row: str(row.expense.id),
        )
    )
    return Reconciliation(scope=scope, items=items, totals=_totals(items))
