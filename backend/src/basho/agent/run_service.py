"""Serviço público de runs do agente (ADR-0001): disparo humano e consulta para o dossiê.

O disparo só **enfileira**: quem executa é o worker. Os campos da tarefa (projeto, pesquisador,
período) vêm do humano que dispara, nunca de inferência; o Maker precisa devolvê-los iguais.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from basho.agent.artifacts import ReportingPeriod
from basho.agent.maker import MakerTask
from basho.agent.run_store import NewRun, RunStore, StoredCall, StoredRun
from basho.agent.runs import DEFAULT_MAX_ATTEMPTS
from basho.agent.tasks import TaskKind, get_profile


@dataclass(frozen=True, slots=True)
class ResearchReportRequest:
    project_id: UUID
    researcher_id: UUID
    period: ReportingPeriod
    requested_by: UUID
    idempotency_key: str | None = None
    is_synthetic: bool = False


@dataclass(frozen=True, slots=True)
class RunDetails:
    stored: StoredRun
    calls: list[StoredCall]

    @property
    def total_cost_usd(self) -> Decimal | None:
        costs = [call.estimated_cost_usd for call in self.calls]
        if not costs or any(cost is None for cost in costs):
            return None
        return sum((cost for cost in costs if cost is not None), Decimal(0))


class AgentRunService:
    def __init__(self, session: AsyncSession) -> None:
        self._store = RunStore(session)

    async def request_research_report(
        self, tenant_id: UUID, request: ResearchReportRequest
    ) -> tuple[StoredRun, bool]:
        """Enfileira um `research_report`. Devolve (run, criado agora?)."""
        profile = get_profile(TaskKind.RESEARCH_REPORT)
        task_input = {
            "project_id": str(request.project_id),
            "researcher_id": str(request.researcher_id),
            "period": request.period.model_dump(mode="json"),
        }
        # Mesma validação que o worker fará: falha aqui, não na fila.
        MakerTask(
            tenant_id=tenant_id,
            run_id=uuid4(),
            project_id=request.project_id,
            profile=profile,
            task_input=task_input,
        )
        new = NewRun(
            tenant_id=tenant_id,
            project_id=request.project_id,
            task_kind=profile.kind,
            prompt_version=profile.prompt_version,
            idempotency_key=request.idempotency_key or f"run:{uuid4().hex}",
            task_input=task_input,
            max_attempts=DEFAULT_MAX_ATTEMPTS,
            requested_by=request.requested_by,
            is_synthetic=request.is_synthetic,
        )
        return await self._store.enqueue(new, at=datetime.now(UTC))

    async def get(self, tenant_id: UUID, run_id: UUID) -> RunDetails:
        stored = await self._store.get(tenant_id, run_id)
        return RunDetails(stored=stored, calls=await self._store.list_calls(tenant_id, run_id))
