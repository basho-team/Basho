"""Custo **estimado** de uma chamada ao modelo (#23), a partir dos tokens do `CallRecord`.

Tabela de preço de lista (USD por milhão de tokens) congelada em 2026-11-08. É estimativa para
o dossiê/telas, não faturamento: descontos, batch e câmbio ficam de fora. Modelo fora da tabela
→ `None` (não inventamos preço). Escrita de cache = 1,25 vezes a entrada (TTL padrão de 5 min).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from basho.agent.llm import CallRecord

PRICES_AS_OF = "2026-11-08"
_PER_TOKEN = Decimal(1) / Decimal(1_000_000)
_QUANTUM = Decimal("0.000001")
_CACHE_WRITE_FACTOR = Decimal("1.25")


@dataclass(frozen=True, slots=True)
class ModelPrice:
    """USD por milhão de tokens."""

    input: Decimal
    output: Decimal
    cache_read: Decimal

    @property
    def cache_write(self) -> Decimal:
        return self.input * _CACHE_WRITE_FACTOR


PRICES: dict[str, ModelPrice] = {
    "claude-opus-5-5": ModelPrice(Decimal(4), Decimal(20), Decimal("0.20")),
    "claude-sonnet-5-5": ModelPrice(Decimal(2), Decimal(10), Decimal("0.20")),
    # Featherless (ADR-0011), /v1/models em 2026-11-08; sem cache de prompt
    "deepseek-ai/DeepSeek-V3.1": ModelPrice(Decimal("0.285"), Decimal(1), Decimal(0)),
    "zai-org/GLM-4.6": ModelPrice(Decimal("0.55"), Decimal("2.2"), Decimal(0)),
    "moonshotai/Kimi-K2-Instruct-0905": ModelPrice(Decimal("0.6"), Decimal("2.5"), Decimal(0)),
}


def estimate_cost_usd(call: CallRecord) -> Decimal | None:
    price = PRICES.get(call.model)
    if price is None:
        return None
    total = (
        call.input_tokens * price.input
        + call.output_tokens * price.output
        + call.cache_read_input_tokens * price.cache_read
        + call.cache_creation_input_tokens * price.cache_write
    ) * _PER_TOKEN
    return total.quantize(_QUANTUM, rounding=ROUND_HALF_UP)
