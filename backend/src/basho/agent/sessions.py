"""Adaptadores de sessão do worker: nenhuma transação fica aberta durante chamadas ao LLM.

O Maker recebe dependências que abrem uma transação **curta** por operação (audit, aprovação,
consulta ao ledger, busca de evidências). A única transação que dura mais de uma operação é a de
persistência (`PersistenceTransaction`): ela é aberta no primeiro `append` do Maker, que só
acontece depois da última chamada ao modelo, e o worker a confirma junto com o fechamento do run
ou a desfaz (ex.: `maker_persist_failed`).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, AsyncSessionTransaction, async_sessionmaker

from basho.agent.approvals import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalView,
    NewApprovalRequest,
    PostgresApprovalStore,
)
from basho.agent.ledger_tools import LedgerEvidenceGateway, LedgerQueryEvents
from basho.agent.tools import ToolResult
from basho.audit import AuditService
from basho.audit.contracts import AuditEntry, NewAuditEntry
from basho.db import TENANT_SETTING, tenant_session
from basho.evidence import EvidenceService
from basho.evidence.contracts import EvidenceEvent, NewEvidenceEvent

Factory = async_sessionmaker[AsyncSession]


class SessionAuditSink:
    """Cada linha de audit na sua própria transação: um rollback posterior não a apaga."""

    def __init__(self, factory: Factory, tenant_id: UUID) -> None:
        self._factory = factory
        self._tenant_id = tenant_id

    async def record(self, entry: NewAuditEntry) -> AuditEntry:
        async with tenant_session(self._factory, self._tenant_id) as session:
            return await AuditService(session).record(entry)


class SessionApprovalStore:
    def __init__(self, factory: Factory, tenant_id: UUID) -> None:
        self._factory = factory
        self._tenant_id = tenant_id

    async def create(self, request: NewApprovalRequest) -> ApprovalRequest:
        async with tenant_session(self._factory, self._tenant_id) as session:
            return await PostgresApprovalStore(session).create(request)

    async def get(self, tenant_id: UUID, approval_id: UUID) -> ApprovalView:
        async with tenant_session(self._factory, self._tenant_id) as session:
            return await PostgresApprovalStore(session).get(tenant_id, approval_id)

    async def decide(
        self, tenant_id: UUID, approval_id: UUID, decision: ApprovalDecision, decided_by: UUID
    ) -> ApprovalView:
        async with tenant_session(self._factory, self._tenant_id) as session:
            return await PostgresApprovalStore(session).decide(
                tenant_id, approval_id, decision, decided_by
            )


class SessionLedgerQueryEvents:
    """`ledger_query_events` real, com uma transação curta por chamada."""

    spec = LedgerQueryEvents.spec

    def __init__(self, factory: Factory, tenant_id: UUID, project_id: UUID) -> None:
        self._factory = factory
        self._tenant_id = tenant_id
        self._project_id = project_id

    async def run(self, tenant_id: str, arguments: dict[str, Any]) -> ToolResult:
        async with tenant_session(self._factory, self._tenant_id) as session:
            tool = LedgerQueryEvents(EvidenceService(session), self._project_id)
            return await tool.run(tenant_id, arguments)


class PersistenceTransaction:
    """`EvidenceGateway` do Maker no worker.

    `get_many` usa transação curta. `append` abre (uma vez) a transação de persistência, que
    fica com o worker: `session` para gravar o fechamento do run nela, `commit()` ou `rollback()`.
    """

    def __init__(self, factory: Factory, tenant_id: UUID) -> None:
        self._factory = factory
        self._tenant_id = tenant_id
        self._session: AsyncSession | None = None
        self._transaction: AsyncSessionTransaction | None = None

    @property
    def session(self) -> AsyncSession | None:
        return self._session

    async def get_many(
        self, tenant_id: UUID, project_id: UUID, ids: Sequence[UUID]
    ) -> list[EvidenceEvent]:
        async with tenant_session(self._factory, self._tenant_id) as session:
            gateway = LedgerEvidenceGateway(EvidenceService(session))
            return await gateway.get_many(tenant_id, project_id, ids)

    async def append(self, event: NewEvidenceEvent) -> EvidenceEvent:
        session = await self._open()
        return await EvidenceService(session).append(event)

    async def _open(self) -> AsyncSession:
        if self._session is None:
            session = self._factory()
            self._transaction = await session.begin()
            await session.execute(
                text("SELECT set_config(:name, :tenant, true)"),
                {"name": TENANT_SETTING, "tenant": str(self._tenant_id)},
            )
            self._session = session
        return self._session

    async def commit(self) -> None:
        await self._close(commit=True)

    async def rollback(self) -> None:
        await self._close(commit=False)

    async def _close(self, *, commit: bool) -> None:
        session, transaction = self._session, self._transaction
        self._session, self._transaction = None, None
        if session is None or transaction is None:
            return
        try:
            if commit:
                await transaction.commit()
            else:
                await transaction.rollback()
        finally:
            await session.close()
