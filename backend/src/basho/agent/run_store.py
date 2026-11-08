"""Persistência de `AgentRun` e fila em Postgres (#10). A transação é do chamador.

A fila é a própria `agent_runs`: `claim_next` reserva o run `queued` mais antigo já liberado
(`run_after <= now`) com `FOR UPDATE SKIP LOCKED`, então dois workers nunca pegam o mesmo run.
Mudança de estado só via `transition_run`/`fail_or_retry` (validadas em código); o UPDATE
confere o estado anterior, então uma transição concorrente não sobrescreve outra.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from basho.agent.costs import estimate_cost_usd
from basho.agent.llm import CallRecord
from basho.agent.models import AgentCallRow, AgentRunRow
from basho.agent.runs import AgentRun, RunError, RunStatus, transition_run
from basho.agent.tasks import TaskKind


class RunNotFoundError(LookupError):
    """Run inexistente neste tenant."""


class StaleRunError(RuntimeError):
    """O run mudou de estado desde a leitura (outra transição venceu)."""


@dataclass(frozen=True, slots=True)
class NewRun:
    tenant_id: UUID
    project_id: UUID
    task_kind: TaskKind
    prompt_version: str
    idempotency_key: str
    task_input: Mapping[str, Any]
    max_attempts: int
    requested_by: UUID | None = None
    is_synthetic: bool = False


@dataclass(frozen=True, slots=True)
class StoredRun:
    """`AgentRun` + o que a fila e o dossiê precisam guardar ao lado dele."""

    run: AgentRun
    project_id: UUID
    task_input: Mapping[str, Any]
    is_synthetic: bool
    run_after: datetime
    requested_by: UUID | None = None
    artifact_event_id: UUID | None = None
    verification_event_id: UUID | None = None
    artifact_status: str | None = None


@dataclass(frozen=True, slots=True)
class StoredCall:
    attempt: int
    seq: int
    record: CallRecord
    estimated_cost_usd: Decimal | None


_ACTIVE = (RunStatus.QUEUED.value, RunStatus.RUNNING.value)


class IdempotencyConflictError(ValueError):
    """`Idempotency-Key` já usada para outra tarefa ou por outro solicitante."""


class TooManyActiveRunsError(RuntimeError):
    """O solicitante atingiu o limite de runs ativos (custo, ADR-0006 §6)."""


def dedupe_key(new: NewRun) -> str:
    """Hash estável da tarefa (tipo + projeto + entrada): um run ativo por tarefa."""
    canonical = json.dumps(
        {
            "task_kind": new.task_kind.value,
            "project_id": str(new.project_id),
            "task_input": new.task_input,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _insert(new: NewRun, dedupe: str, at: datetime) -> Any:
    return (
        pg_insert(AgentRunRow)
        .values(
            id=uuid4(),
            tenant_id=new.tenant_id,
            project_id=new.project_id,
            task_kind=new.task_kind.value,
            prompt_version=new.prompt_version,
            status=RunStatus.QUEUED.value,
            correlation_id=uuid4(),
            idempotency_key=new.idempotency_key,
            dedupe_key=dedupe,
            attempts=0,
            max_attempts=new.max_attempts,
            task_input=dict(new.task_input),
            requested_by=new.requested_by,
            is_synthetic=new.is_synthetic,
            run_after=at,
            created_at=at,
            updated_at=at,
        )
        .on_conflict_do_nothing()
        .returning(AgentRunRow)
    )


def _to_stored(row: AgentRunRow) -> StoredRun:
    run = AgentRun(
        id=row.id,
        tenant_id=row.tenant_id,
        task_kind=TaskKind(row.task_kind),
        prompt_version=row.prompt_version,
        status=RunStatus(row.status),
        correlation_id=row.correlation_id,
        parent_run_id=row.parent_run_id,
        idempotency_key=row.idempotency_key,
        attempts=row.attempts,
        max_attempts=row.max_attempts,
        created_at=row.created_at,
        updated_at=row.updated_at,
        error=RunError.model_validate(row.error) if row.error is not None else None,
    )
    return StoredRun(
        run=run,
        project_id=row.project_id,
        task_input=dict(row.task_input),
        is_synthetic=row.is_synthetic,
        run_after=row.run_after,
        requested_by=row.requested_by,
        artifact_event_id=row.artifact_event_id,
        verification_event_id=row.verification_event_id,
        artifact_status=row.artifact_status,
    )


class RunStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def enqueue(
        self, new: NewRun, *, at: datetime, max_active_per_requester: int | None = None
    ) -> tuple[StoredRun, bool]:
        """Cria o run `queued` ou devolve o existente (run, criado agora?).

        - `idempotency_key` repetida com outra tarefa/solicitante → `IdempotencyConflictError`;
        - já há run ativo (`queued`/`running`) para a mesma tarefa → devolve esse run;
        - solicitante com `max_active_per_requester` runs ativos → `TooManyActiveRunsError`.
        """
        dedupe = dedupe_key(new)
        for _ in range(2):  # 2ª volta só se outro INSERT concorrente vencer o índice único
            existing = await self._existing(new, dedupe)
            if existing is not None:
                return existing, False
            if new.requested_by is not None and max_active_per_requester is not None:
                active = await self._count_active(new.tenant_id, new.requested_by)
                if active >= max_active_per_requester:
                    raise TooManyActiveRunsError(str(new.requested_by))
            created = (await self._session.execute(_insert(new, dedupe, at))).scalar_one_or_none()
            if created is not None:
                return _to_stored(created), True
        raise StaleRunError("conflito ao enfileirar o run")

    async def _existing(self, new: NewRun, dedupe: str) -> StoredRun | None:
        by_key = (
            await self._session.execute(
                select(AgentRunRow).where(
                    AgentRunRow.tenant_id == new.tenant_id,
                    AgentRunRow.idempotency_key == new.idempotency_key,
                )
            )
        ).scalar_one_or_none()
        if by_key is not None:
            if by_key.dedupe_key != dedupe or by_key.requested_by != new.requested_by:
                raise IdempotencyConflictError(new.idempotency_key)
            return _to_stored(by_key)
        active = (
            await self._session.execute(
                select(AgentRunRow).where(
                    AgentRunRow.tenant_id == new.tenant_id,
                    AgentRunRow.dedupe_key == dedupe,
                    AgentRunRow.status.in_(_ACTIVE),
                )
            )
        ).scalar_one_or_none()
        return _to_stored(active) if active is not None else None

    async def _count_active(self, tenant_id: UUID, requested_by: UUID) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(AgentRunRow)
            .where(
                AgentRunRow.tenant_id == tenant_id,
                AgentRunRow.requested_by == requested_by,
                AgentRunRow.status.in_(_ACTIVE),
            )
        )
        return int(result.scalar_one())

    async def get(self, tenant_id: UUID, run_id: UUID) -> StoredRun:
        row = (
            await self._session.execute(
                select(AgentRunRow).where(
                    AgentRunRow.tenant_id == tenant_id, AgentRunRow.id == run_id
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise RunNotFoundError(str(run_id))
        return _to_stored(row)

    async def claim_next(self, tenant_id: UUID, *, at: datetime) -> StoredRun | None:
        """Reserva o próximo run liberado e o marca `running` (conta uma tentativa)."""
        row = (
            await self._session.execute(
                select(AgentRunRow)
                .where(
                    AgentRunRow.tenant_id == tenant_id,
                    AgentRunRow.status == RunStatus.QUEUED.value,
                    AgentRunRow.run_after <= at,
                )
                .order_by(AgentRunRow.run_after, AgentRunRow.created_at)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        stored = _to_stored(row)
        return await self.save(stored, transition_run(stored.run, RunStatus.RUNNING, at=at))

    async def save(
        self,
        stored: StoredRun,
        new_run: AgentRun,
        *,
        run_after: datetime | None = None,
        artifact_event_id: UUID | None = None,
        verification_event_id: UUID | None = None,
        artifact_status: str | None = None,
    ) -> StoredRun:
        """Grava uma transição já validada; falha se o estado mudou desde a leitura."""
        values: dict[str, Any] = {
            "status": new_run.status.value,
            "attempts": new_run.attempts,
            "error": new_run.error.model_dump() if new_run.error is not None else None,
            "updated_at": new_run.updated_at,
            "run_after": run_after if run_after is not None else stored.run_after,
            "artifact_event_id": artifact_event_id or stored.artifact_event_id,
            "verification_event_id": verification_event_id or stored.verification_event_id,
            "artifact_status": artifact_status or stored.artifact_status,
        }
        result = await self._session.execute(
            update(AgentRunRow)
            .where(
                AgentRunRow.tenant_id == stored.run.tenant_id,
                AgentRunRow.id == stored.run.id,
                AgentRunRow.status == stored.run.status.value,
            )
            .values(**values)
            .returning(AgentRunRow)
            .execution_options(populate_existing=True)
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise StaleRunError(str(stored.run.id))
        return _to_stored(row)

    async def record_calls(self, run: AgentRun, attempt: int, calls: Sequence[CallRecord]) -> None:
        if not calls:
            return
        await self._session.execute(
            insert(AgentCallRow),
            [
                {
                    "id": uuid4(),
                    "tenant_id": run.tenant_id,
                    "run_id": run.id,
                    "attempt": attempt,
                    "seq": seq,
                    **call.model_dump(),
                    "estimated_cost_usd": estimate_cost_usd(call),
                }
                for seq, call in enumerate(calls)
            ],
        )

    async def list_calls(self, tenant_id: UUID, run_id: UUID) -> list[StoredCall]:
        rows = (
            await self._session.execute(
                select(AgentCallRow)
                .where(AgentCallRow.tenant_id == tenant_id, AgentCallRow.run_id == run_id)
                .order_by(AgentCallRow.attempt, AgentCallRow.seq)
            )
        ).scalars()
        return [
            StoredCall(
                attempt=row.attempt,
                seq=row.seq,
                record=CallRecord(
                    model=row.model,
                    prompt_version=row.prompt_version,
                    stop_reason=row.stop_reason,
                    input_tokens=row.input_tokens,
                    output_tokens=row.output_tokens,
                    cache_read_input_tokens=row.cache_read_input_tokens,
                    cache_creation_input_tokens=row.cache_creation_input_tokens,
                    latency_ms=row.latency_ms,
                    request_id=row.request_id,
                ),
                estimated_cost_usd=row.estimated_cost_usd,
            )
            for row in rows
        ]
