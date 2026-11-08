"""Persistência de `AgentRun` e fila em Postgres (#10). A transação é do chamador.

A fila é a própria `agent_runs`: `claim_next` reserva o run `queued` mais antigo já liberado
(`run_after <= now`) com `FOR UPDATE SKIP LOCKED`, então dois workers nunca pegam o mesmo run.
Mudança de estado só via `transition_run`/`fail_or_retry` (validadas em código); o UPDATE
confere o estado anterior, então uma transição concorrente não sobrescreve outra.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import insert, select, update
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

    async def enqueue(self, new: NewRun, *, at: datetime) -> tuple[StoredRun, bool]:
        """Cria o run `queued`. Mesma `idempotency_key` no tenant → devolve o existente."""
        statement = (
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
                attempts=0,
                max_attempts=new.max_attempts,
                task_input=dict(new.task_input),
                requested_by=new.requested_by,
                is_synthetic=new.is_synthetic,
                run_after=at,
                created_at=at,
                updated_at=at,
            )
            .on_conflict_do_nothing(constraint="uq_agent_runs_idempotency")
            .returning(AgentRunRow)
        )
        created = (await self._session.execute(statement)).scalar_one_or_none()
        if created is not None:
            return _to_stored(created), True
        existing = await self._session.execute(
            select(AgentRunRow).where(
                AgentRunRow.tenant_id == new.tenant_id,
                AgentRunRow.idempotency_key == new.idempotency_key,
            )
        )
        return _to_stored(existing.scalar_one()), False

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
