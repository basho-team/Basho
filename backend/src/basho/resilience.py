"""Retry com backoff exponencial e jitter para chamadas a provedores externos (#25).

Só falha transitória é repetida; quem decide é o chamador (`is_retryable`). O módulo não sabe
nada de GitHub nem de LLM: recebe a operação, a política e, opcionalmente, quanto o provedor
pediu para esperar (`Retry-After`). `sleep` e `rng` são injetáveis para o teste não esperar.

Regra de segurança: este helper serve a operações **sem efeito externo** (leituras) ou que o
chamador já tornou idempotentes. Escrita com efeito só é repetida depois de consultar o destino
(ver `GithubClient.ensure_issue`).
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """`max_attempts` conta a primeira tentativa (3 = 1 original + 2 repetições)."""

    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    jitter: float = 0.25
    """Fração do atraso sorteada para mais ou para menos (0.25 = ±25%)."""

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts deve ser >= 1")
        if self.base_delay < 0 or self.max_delay < self.base_delay:
            raise ValueError("atrasos inválidos: 0 <= base_delay <= max_delay")
        if not 0 <= self.jitter <= 1:
            raise ValueError("jitter deve estar entre 0 e 1")

    def delay(self, attempt: int, *, rng: Callable[[], float] = random.random) -> float:
        """Atraso antes da tentativa seguinte; `attempt` é a que acabou de falhar (1-based)."""
        raw = min(self.base_delay * 2.0 ** max(attempt - 1, 0), self.max_delay)
        spread = raw * self.jitter
        return max(0.0, min(raw + (rng() * 2 - 1) * spread, self.max_delay))

    def next_delay(
        self,
        attempt: int,
        requested: float | None = None,
        *,
        rng: Callable[[], float] = random.random,
    ) -> float | None:
        """Atraso até a próxima tentativa, ou `None` se não vale esperar.

        `requested` é a espera pedida pelo provedor (`Retry-After`). Se passar de `max_delay`,
        o processo não fica parado: devolve `None` e quem agenda (worker) reprograma o run.
        """
        if requested is not None and requested > self.max_delay:
            return None
        backoff = self.delay(attempt, rng=rng)
        return backoff if requested is None else max(backoff, requested)


NO_RETRY = RetryPolicy(max_attempts=1)


async def call_with_retry[T](
    operation: Callable[[], Awaitable[T]],
    *,
    policy: RetryPolicy,
    is_retryable: Callable[[Exception], bool],
    retry_after: Callable[[Exception], float | None] = lambda _exc: None,
    on_retry: Callable[[int, Exception, float], None] | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    rng: Callable[[], float] = random.random,
) -> T:
    """Executa `operation`; repete erro transitório até `policy.max_attempts`.

    Sobe a **última** exceção ao esgotar, sem engolir nada. Erro permanente sobe na hora.
    Se o provedor pediu espera maior que `policy.max_delay`, sobe sem esperar.
    """
    attempt = 1
    while True:
        try:
            return await operation()
        except Exception as exc:
            if attempt >= policy.max_attempts or not is_retryable(exc):
                raise
            delay = policy.next_delay(attempt, retry_after(exc), rng=rng)
            if delay is None:
                raise
            if on_retry is not None:
                on_retry(attempt, exc, delay)
            await sleep(delay)
            attempt += 1
