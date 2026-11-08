"""Tipos internos experimentais. Não são contratos HTTP nem prova de confirmação humana."""

from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)


class Scope(FrozenModel):
    tenant_id: UUID
    project_id: UUID
    fiscal_year: int = Field(ge=2005, le=9999)


class SourceRef(FrozenModel):
    """Localizador versionado fornecido por adaptador autorizado; não concede acesso."""

    tenant_id: UUID
    project_id: UUID
    reference: str = Field(min_length=1)
    revision: str = Field(min_length=1)
    locator: str = Field(min_length=1)
    origin: Literal["user", "formal_system", "document", "github"]


def cents(value: Decimal) -> int:
    """Converte sem arredondar e sem depender do contexto decimal do processo."""
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError("Valor deve ser Decimal finito")
    if value < 0 or value > Decimal("999999999999999.99"):
        raise ValueError("Valor fora dos limites de conciliação")
    _, digits, exponent = value.as_tuple()
    if not isinstance(exponent, int):
        raise ValueError("Expoente monetário inválido")
    coefficient = int("".join(map(str, digits)))
    if coefficient == 0:
        return 0
    if exponent >= -2:
        return int(coefficient * pow(10, exponent + 2))
    if -exponent - 2 >= len(digits):
        raise ValueError("Precisão monetária superior a dois decimais")
    divisor = int(pow(10, -exponent - 2))
    if coefficient % divisor:
        raise ValueError("Precisão monetária superior a dois decimais")
    return coefficient // divisor


def money(value: int) -> Decimal:
    return Decimal(f"{value // 100}.{value % 100:02d}")


class Allocation(FrozenModel):
    activity_id: UUID
    amount: Decimal = Field(strict=True)
    basis: str = Field(min_length=1)
    sources: tuple[SourceRef, ...] = ()

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, value: Decimal) -> Decimal:
        cents(value)
        return value


class Expense(FrozenModel):
    id: UUID
    scope: Scope
    # Chave explícita do mesmo item econômico, definida na origem; nunca dedução por texto.
    economic_item_ref: str | None = Field(default=None, min_length=1)
    period_start: date
    period_end: date
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    amount: Decimal | None = Field(default=None, strict=True)
    attributable_limit: Decimal | None = Field(default=None, strict=True)
    allocations: tuple[Allocation, ...] = ()
    sources: tuple[SourceRef, ...] = ()
    confirmed: bool = False
    excluded_reason: str | None = Field(default=None, min_length=1)
    is_synthetic: bool = False

    @field_validator("amount", "attributable_limit")
    @classmethod
    def validate_money(cls, value: Decimal | None) -> Decimal | None:
        if value is not None:
            cents(value)
        return value

    @model_validator(mode="after")
    def ordered_period(self) -> Self:
        if self.period_end < self.period_start:
            raise ValueError("Período invertido")
        return self


class ReconciliationState(StrEnum):
    CONSISTENT = "consistent"
    PENDING = "pending"
    CONFLICT = "conflict"
    DUPLICATE = "duplicate"
    EXCLUDED = "excluded"


class ReconciledItem(FrozenModel):
    expense: Expense
    state: ReconciliationState
    gaps: tuple[str, ...]
    duplicate_of: UUID | None = None
    # Nenhum destes valores é total fiscal elegível.
    proposed_amount: Decimal | None = Field(default=None, strict=True)
    unallocated_amount: Decimal | None = Field(default=None, strict=True)


class CurrencyTotal(FrozenModel):
    currency: str
    consistent_proposed: Decimal
    pending_known: Decimal
    pending_unknown_count: int


class Reconciliation(FrozenModel):
    scope: Scope
    items: tuple[ReconciledItem, ...]
    totals: tuple[CurrencyTotal, ...]
