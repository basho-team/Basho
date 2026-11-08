"""Retry com backoff e jitter (#25): só falha transitória, sem engolir erro."""

from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from basho.resilience import RetryPolicy, call_with_retry


class TransientError(Exception):
    def __init__(self, retry_after: float | None = None) -> None:
        super().__init__("transitório")
        self.retry_after = retry_after


class PermanentError(Exception):
    pass


class Recorder:
    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)


def _retryable(exc: Exception) -> bool:
    return isinstance(exc, TransientError)


def _after(exc: Exception) -> float | None:
    return exc.retry_after if isinstance(exc, TransientError) else None


def _flaky(failures: list[Exception]) -> tuple[list[int], Callable[[], Awaitable[str]]]:
    calls: list[int] = []

    async def operation() -> str:
        calls.append(1)
        if failures:
            raise failures.pop(0)
        return "ok"

    return calls, operation


async def test_transient_failure_is_recovered_by_retry() -> None:
    # Arrange
    sleeps = Recorder()
    calls, operation = _flaky([TransientError(), TransientError()])
    policy = RetryPolicy(max_attempts=3, base_delay=1.0, jitter=0.0)

    # Act
    result = await call_with_retry(
        operation,
        policy=policy,
        is_retryable=_retryable,
        sleep=sleeps,
    )

    # Assert: backoff exponencial 1s, 2s
    assert result == "ok"
    assert len(calls) == 3
    assert sleeps.delays == [1.0, 2.0]


async def test_permanent_failure_is_raised_without_retry() -> None:
    sleeps = Recorder()
    calls, operation = _flaky([PermanentError()])
    with pytest.raises(PermanentError):
        await call_with_retry(
            operation,
            policy=RetryPolicy(),
            is_retryable=_retryable,
            sleep=sleeps,
        )
    assert len(calls) == 1
    assert sleeps.delays == []


async def test_exhausted_attempts_raise_the_last_error_not_swallow_it() -> None:
    sleeps = Recorder()
    calls, operation = _flaky(
        [TransientError(), TransientError(), TransientError(), TransientError()]
    )
    with pytest.raises(TransientError):
        await call_with_retry(
            operation,
            policy=RetryPolicy(max_attempts=3, jitter=0.0),
            is_retryable=_retryable,
            sleep=sleeps,
        )
    assert len(calls) == 3
    assert len(sleeps.delays) == 2


async def test_retry_after_is_respected_when_longer_than_backoff() -> None:
    sleeps = Recorder()
    _, operation = _flaky([TransientError(retry_after=30.0)])
    await call_with_retry(
        operation,
        policy=RetryPolicy(base_delay=1.0, max_delay=60.0, jitter=0.0),
        is_retryable=_retryable,
        retry_after=_after,
        sleep=sleeps,
    )
    assert sleeps.delays == [30.0]


async def test_retry_after_beyond_max_delay_gives_up_without_waiting() -> None:
    # O worker reagenda; o processo não fica parado por 10 minutos.
    sleeps = Recorder()
    calls, operation = _flaky([TransientError(retry_after=600.0)])
    with pytest.raises(TransientError):
        await call_with_retry(
            operation,
            policy=RetryPolicy(max_delay=60.0),
            is_retryable=_retryable,
            retry_after=_after,
            sleep=sleeps,
        )
    assert len(calls) == 1
    assert sleeps.delays == []


def test_delay_grows_exponentially_is_capped_and_jitter_stays_in_bounds() -> None:
    policy = RetryPolicy(base_delay=1.0, max_delay=10.0, jitter=0.25)
    assert policy.delay(1, rng=lambda: 0.5) == 1.0
    assert policy.delay(3, rng=lambda: 0.5) == 4.0
    assert policy.delay(10, rng=lambda: 0.5) == 10.0  # teto
    assert policy.delay(3, rng=lambda: 0.0) == 3.0  # -25%
    assert policy.delay(3, rng=lambda: 1.0) == 5.0  # +25%
    assert policy.delay(10, rng=lambda: 1.0) == 10.0  # jitter nunca passa do teto


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_attempts": 0},
        {"base_delay": -1.0},
        {"base_delay": 5.0, "max_delay": 1.0},
        {"jitter": 2},
    ],
)
def test_invalid_policy_is_rejected(kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match=r"max_attempts|atrasos|jitter"):
        RetryPolicy(**kwargs)
