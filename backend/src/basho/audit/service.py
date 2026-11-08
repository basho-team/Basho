"""Serviço público do audit log: somente INSERT e SELECT (ADR-0005, ADR-0006).

A transação pertence ao chamador (``tenant_session``), como no ledger: o audit de uma chamada
é gravado na mesma transação do efeito interno que ela produz.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

from sqlalchemy import insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from basho.audit.contracts import AuditEntry, InputSummary, NewAuditEntry
from basho.audit.models import AuditLogRow


class AuditError(RuntimeError):
    """Falha ao gravar ou ler o audit log."""


class AuditSink(Protocol):
    """Destino do audit. A policy depende só deste protocolo."""

    async def record(self, entry: NewAuditEntry) -> AuditEntry: ...


class InMemoryAuditLog:
    """Audit em memória para testes e para o modo simulado. Append-only por construção."""

    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []

    @property
    def entries(self) -> tuple[AuditEntry, ...]:
        return tuple(self._entries)

    async def record(self, entry: NewAuditEntry) -> AuditEntry:
        saved = AuditEntry(**entry.model_dump(), id=uuid4(), created_at=datetime.now(UTC))
        self._entries.append(saved)
        return saved


def _to_entry(row: AuditLogRow) -> AuditEntry:
    return AuditEntry.model_validate(
        {
            "id": row.id,
            "tenant_id": row.tenant_id,
            "event_type": row.event_type,
            "actor_type": row.actor_type,
            "actor_id": row.actor_id,
            "run_id": row.run_id,
            "tool": row.tool,
            "level": row.level,
            "decision": row.decision,
            "outcome": row.outcome,
            "reason_code": row.reason_code,
            "input_summary": InputSummary(
                keys=tuple(row.input_keys), size_bytes=row.input_size_bytes
            ),
            "approval_id": row.approval_id,
            "created_at": row.created_at,
        }
    )


def _insert_values(entry: NewAuditEntry) -> dict[str, Any]:
    return {
        "id": uuid4(),
        "tenant_id": entry.tenant_id,
        "event_type": entry.event_type.value,
        "actor_type": entry.actor_type.value,
        "actor_id": entry.actor_id,
        "run_id": entry.run_id,
        "tool": entry.tool,
        "level": entry.level.value if entry.level else None,
        "decision": entry.decision.value,
        "outcome": entry.outcome.value,
        "reason_code": entry.reason_code,
        "input_keys": list(entry.input_summary.keys),
        "input_size_bytes": entry.input_summary.size_bytes,
        "approval_id": entry.approval_id,
    }


class AuditService:
    """Audit em Postgres (`audit_log`, append-only por trigger e GRANT)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _require_session_tenant(self, tenant_id: UUID) -> None:
        result = await self._session.execute(text("SELECT current_setting('app.tenant_id', true)"))
        if result.scalar_one_or_none() != str(tenant_id):
            raise AuditError("tenant da sessão ausente ou diferente do informado")

    async def record(self, entry: NewAuditEntry) -> AuditEntry:
        await self._require_session_tenant(entry.tenant_id)
        statement = insert(AuditLogRow).values(**_insert_values(entry)).returning(AuditLogRow)
        result = await self._session.execute(statement)
        return _to_entry(result.scalar_one())

    async def list_for_run(self, tenant_id: UUID, run_id: UUID) -> list[AuditEntry]:
        await self._require_session_tenant(tenant_id)
        statement = (
            select(AuditLogRow)
            .where(AuditLogRow.tenant_id == tenant_id, AuditLogRow.run_id == run_id)
            .order_by(AuditLogRow.created_at, AuditLogRow.id)
        )
        return [_to_entry(row) for row in (await self._session.execute(statement)).scalars()]
