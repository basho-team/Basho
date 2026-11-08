"""Worker do agente (#10): reserva runs da fila e executa o Maker, um run por vez.

Processo separado da API, com login membro de `basho_worker` (`python -m basho.agent.worker`).
Ciclo de um run:

1. transação curta: `claim_next` (`FOR UPDATE SKIP LOCKED`) → `running`;
2. `Maker.run` **sem transação aberta**: audit, aprovações e consultas abrem transações curtas
   próprias (`agent/sessions.py`);
3. concluído: os eventos do Maker, os `CallRecord` e o `completed` vão na mesma transação de
   persistência (atômico). Qualquer falha desfaz essa transação (inclusive
   `maker_persist_failed`) e grava, numa transação nova, os `CallRecord` + `fail_or_retry`:
   erro retryable com tentativas restantes volta à fila com backoff exponencial (#25).

MVP single-tenant: o worker atende `Settings.tenant_id` (a RLS restringe a fila a ele). Run
preso em `running` após queda do processo não é recuperado automaticamente (backlog).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from basho.agent.checks import ReportDeterministicChecker
from basho.agent.llm import MessagesClient, ModelSettings
from basho.agent.maker import Maker, MakerResult, MakerStatus, MakerTask
from basho.agent.policy import ToolPolicy
from basho.agent.registry import ToolRegistry
from basho.agent.run_store import RunStore, StoredRun
from basho.agent.runs import AgentRun, RunError, RunStatus, fail_or_retry, transition_run
from basho.agent.sessions import (
    PersistenceTransaction,
    SessionApprovalStore,
    SessionAuditSink,
    SessionLedgerQueryEvents,
)
from basho.agent.simulated_tools import (
    GithubCreateIssue,
    GithubFixtures,
    GithubGetPullRequest,
    GithubListCommits,
    LedgerRecordDraft,
    PendingItemOpen,
    SimulatedInternalStore,
)
from basho.agent.tasks import ProfileNotAvailableError, get_profile
from basho.agent.tools import Tool
from basho.agent.verifier import Verifier
from basho.config import Settings
from basho.db import tenant_session
from basho.logging import get_logger

BACKOFF_BASE_SECONDS = 5
BACKOFF_MAX_SECONDS = 300
POLL_INTERVAL_SECONDS = 2.0
INVALID_TASK = "worker_invalid_task"
UNEXPECTED_ERROR = "worker_unexpected_error"
COMMIT_FAILED = "worker_commit_failed"

logger = get_logger(__name__)
Factory = async_sessionmaker[AsyncSession]
Clock = Callable[[], datetime]


def model_settings_from(settings: Settings) -> ModelSettings:
    """Ponte `Settings` (env) → `ModelSettings` do Maker."""
    return ModelSettings(model=settings.maker_model, effort=settings.maker_effort)


def retry_delay(attempts: int) -> timedelta:
    """Backoff exponencial com teto: 5 s, 10 s, 20 s... até 5 min."""
    seconds = BACKOFF_BASE_SECONDS * 2 ** max(attempts - 1, 0)
    return timedelta(seconds=min(seconds, BACKOFF_MAX_SECONDS))


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class WorkerConfig:
    tenant_id: UUID
    model: ModelSettings
    github_fixtures: GithubFixtures | None = None


class Worker:
    def __init__(
        self,
        *,
        factory: Factory,
        client: MessagesClient,
        verifier: Verifier,
        config: WorkerConfig,
        clock: Clock = _utcnow,
    ) -> None:
        self._factory = factory
        self._client = client
        self._verifier = verifier
        self._config = config
        self._clock = clock

    async def process_one(self) -> UUID | None:
        """Processa um run liberado; `None` se a fila estiver vazia."""
        tenant_id = self._config.tenant_id
        async with tenant_session(self._factory, tenant_id) as session:
            stored = await RunStore(session).claim_next(tenant_id, at=self._clock())
        if stored is None:
            return None
        log = logger.bind(
            run_id=str(stored.run.id),
            correlation_id=str(stored.run.correlation_id),
            attempt=stored.run.attempts,
        )
        log.info("agent_run_started", task_kind=stored.run.task_kind.value)
        persistence = PersistenceTransaction(self._factory, tenant_id)
        try:
            task = self._task(stored)
        except (ValueError, ProfileNotAvailableError):
            error = RunError(code=INVALID_TASK, message="tarefa inválida", retryable=False)
            await self._fail(stored, error, MakerResult(MakerStatus.FAILED, (), 0))
            return stored.run.id
        try:
            result = await self._maker(stored, persistence).run(task)
        except Exception as exc:  # falha explícita: registrada no run, nunca engolida em silêncio
            await persistence.rollback()
            log.error("agent_run_crashed", error_type=type(exc).__name__)
            error = RunError(code=UNEXPECTED_ERROR, message=type(exc).__name__, retryable=False)
            await self._fail(stored, error, MakerResult(MakerStatus.FAILED, (), 0))
            return stored.run.id
        if result.status is MakerStatus.COMPLETED:
            await self._complete(stored, result, persistence)
        else:
            await persistence.rollback()
            error = result.error or RunError(
                code=UNEXPECTED_ERROR, message="Maker terminou sem erro", retryable=False
            )
            await self._fail(stored, error, result)
        return stored.run.id

    def _task(self, stored: StoredRun) -> MakerTask:
        profile = get_profile(stored.run.task_kind)
        if profile.prompt_version != stored.run.prompt_version:
            raise ValueError("versão de prompt do run difere do perfil atual")
        return MakerTask(
            tenant_id=stored.run.tenant_id,
            run_id=stored.run.id,
            project_id=stored.project_id,
            profile=profile,
            task_input=stored.task_input,
            is_synthetic=stored.is_synthetic,
        )

    def _maker(self, stored: StoredRun, persistence: PersistenceTransaction) -> Maker:
        tenant_id = self._config.tenant_id
        registry = ToolRegistry(self._tools(stored.project_id))
        policy = ToolPolicy(
            registry,
            SessionAuditSink(self._factory, tenant_id),
            SessionApprovalStore(self._factory, tenant_id),
        )
        return Maker(
            client=self._client,
            registry=registry,
            policy=policy,
            checker=ReportDeterministicChecker(tenant_id),
            verifier=self._verifier,
            evidence=persistence,
            settings=self._config.model,
        )

    def _tools(self, project_id: UUID) -> list[Tool]:
        """Ledger real; GitHub e registros internos simulados até o #7 e as projeções (#5)."""
        internal = SimulatedInternalStore()
        tools: list[Tool] = [
            SessionLedgerQueryEvents(self._factory, self._config.tenant_id, project_id),
            LedgerRecordDraft(internal),
            PendingItemOpen(internal),
            GithubCreateIssue(),
        ]
        fixtures = self._config.github_fixtures
        if fixtures is not None:
            tools += [GithubListCommits(fixtures), GithubGetPullRequest(fixtures)]
        return tools

    async def _complete(
        self,
        stored: StoredRun,
        result: MakerResult,
        persistence: PersistenceTransaction,
    ) -> None:
        session = persistence.session
        outcome = result.outcome
        try:
            if session is None or outcome is None:
                raise RuntimeError("Maker concluiu sem gravar artefato")
            store = RunStore(session)
            await store.record_calls(stored.run, stored.run.attempts, result.calls)
            done = transition_run(stored.run, RunStatus.COMPLETED, at=self._clock())
            await store.save(
                stored,
                done,
                artifact_event_id=result.artifact_event_id,
                verification_event_id=result.verification_event_id,
                artifact_status=outcome.status.value,
            )
            await persistence.commit()
        except Exception as exc:
            await persistence.rollback()
            logger.error(
                "agent_run_commit_failed", run_id=str(stored.run.id), error_type=type(exc).__name__
            )
            # Não retryable: se o COMMIT chegou ao servidor e só a resposta se perdeu,
            # refazer duplicaria artefato e verificação no ledger.
            error = RunError(code=COMMIT_FAILED, message=type(exc).__name__, retryable=False)
            await self._fail(stored, error, result)
            return
        logger.info(
            "agent_run_completed",
            run_id=str(stored.run.id),
            artifact_status=outcome.status.value,
            calls=len(result.calls),
        )

    async def _fail(self, stored: StoredRun, error: RunError, result: MakerResult) -> AgentRun:
        now = self._clock()
        next_run = fail_or_retry(stored.run, error, at=now)
        run_after = (
            now + retry_delay(next_run.attempts) if next_run.status is RunStatus.QUEUED else None
        )
        async with tenant_session(self._factory, self._config.tenant_id) as session:
            store = RunStore(session)
            await store.record_calls(stored.run, stored.run.attempts, result.calls)
            await store.save(stored, next_run, run_after=run_after)
        logger.warning(
            "agent_run_failed" if next_run.status is RunStatus.FAILED else "agent_run_retry",
            run_id=str(stored.run.id),
            error_code=error.code,
            attempts=next_run.attempts,
        )
        return next_run


async def run_forever(settings: Settings) -> None:  # pragma: no cover - processo real
    """Entry point do processo worker: valida o role, monta clientes e consome a fila."""
    import anthropic

    from basho.agent.checker import ClaudeVerifier, FallbackVerifier, OpenAICompatibleVerifier
    from basho.db import (
        API_ROLE,
        WORKER_ROLE,
        assert_least_privilege,
        assert_process_role,
        create_engine,
        create_session_factory,
    )

    engine = create_engine(settings.database_url.get_secret_value())
    await assert_least_privilege(engine)
    await assert_process_role(engine, required=WORKER_ROLE, forbidden=API_ROLE)
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key.get_secret_value())
    verifier = FallbackVerifier(
        OpenAICompatibleVerifier(
            base_url=str(settings.featherless_base_url),
            api_key=settings.featherless_api_key,
            model_id=settings.checker_model,
        ),
        ClaudeVerifier(client=client, maker_model=settings.maker_model),
    )
    fixtures = (
        GithubFixtures.load(Path(settings.github_fixtures_dir))
        if settings.github_fixtures_dir is not None
        else None
    )
    worker = Worker(
        factory=create_session_factory(engine),
        client=client,
        verifier=verifier,
        config=WorkerConfig(settings.tenant_id, model_settings_from(settings), fixtures),
    )
    logger.info("agent_worker_started")
    try:
        failures = 0
        while True:
            try:
                processed = await worker.process_one()
                failures = 0
            except Exception as exc:  # banco fora, StaleRunError...: loga e espera, sem morrer
                failures += 1
                logger.error("agent_worker_loop_error", error_type=type(exc).__name__)
                await asyncio.sleep(retry_delay(failures).total_seconds())
                continue
            if processed is None:
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
    finally:
        await engine.dispose()


def main() -> None:  # pragma: no cover - processo real
    from basho.config import get_settings
    from basho.logging import configure_logging

    configure_logging()
    asyncio.run(run_forever(get_settings()))


if __name__ == "__main__":  # pragma: no cover
    main()
