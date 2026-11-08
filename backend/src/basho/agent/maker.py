"""Maker: Claude com tool use para um perfil de tarefa (ADR-0004, ADR-0005, ADR-0009).

Loop manual (não o Tool Runner) porque toda chamada de tool passa pela `ToolPolicy` (gate +
audit) e porque validação, retries e persistência são decididos por código:

1. o modelo investiga com as tools do allowlist do perfil;
2. a resposta final é JSON validado pelo `output_schema` do perfil e pelos campos da tarefa;
3. checks determinísticos + Checker independente (`verify_artifact`, #9);
4. saída inválida ou `maker_should_retry` → o Maker refaz, no máximo `MAX_REDOS` vezes;
   esgotado, termina em `invalid_output` **sem gravar** (rascunho reprovado não vira evidência);
5. o rascunho aprovado nos checks e o resultado da verificação viram eventos no ledger
   (actor `maker` + modelo), com status `verified` ou `needs_human`.

O Maker nunca decide estado formal: o artefato gravado fica em `verified` ou `needs_human`.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel

from basho.agent.checker import (
    VerificationOutcome,
    VerifierUnavailableError,
    verification_event,
    verify_artifact,
)
from basho.agent.checks import cited_evidence_ids
from basho.agent.llm import (
    CallRecord,
    MakerProviderError,
    MessagesClient,
    ModelSettings,
    create_message,
    system_blocks,
    tool_definitions,
)
from basho.agent.maker_output import (
    TRUNCATED,
    OutputProblem,
    checks_feedback,
    output_feedback,
    parse_output,
    truncated_feedback,
)
from basho.agent.policy import ToolCallContext, ToolPolicy
from basho.agent.registry import ToolRegistry
from basho.agent.runs import RunError
from basho.agent.tasks import TaskProfile, load_prompt
from basho.agent.tools import ToolCallStatus
from basho.agent.verifier import DeterministicChecker, VerifiableArtifact, Verifier
from basho.evidence import EvidenceValidationError
from basho.evidence.contracts import (
    Actor,
    ActorType,
    EventKind,
    EventSource,
    EvidenceEvent,
    NewEvidenceEvent,
)

MAX_REDOS = 2
"""Quantas vezes o Maker refaz após saída inválida ou falha determinística (3 tentativas)."""
MAX_TOOL_TURNS = 12
MAKER_ACTOR_ID = "maker"
CHECKS_FAILED = "maker_checks_failed"
PERSIST_FAILED = "maker_persist_failed"


class MakerStatus(StrEnum):
    """Estado de **execução** do Maker; o estado do artefato vem de `VerificationOutcome`."""

    COMPLETED = "completed"
    REFUSED = "refused"
    INVALID_OUTPUT = "invalid_output"
    FAILED = "failed"


class EvidenceGateway(Protocol):
    """Acesso do Maker ao ledger (implementado sobre o `EvidenceService`)."""

    async def get_many(
        self, tenant_id: UUID, project_id: UUID, ids: Sequence[UUID]
    ) -> list[EvidenceEvent]: ...

    async def append(self, event: NewEvidenceEvent) -> EvidenceEvent: ...


@dataclass(frozen=True, slots=True)
class MakerTask:
    """Uma execução do Maker. `task_input` é gerado pelo sistema (confiável) e em JSON."""

    tenant_id: UUID
    run_id: UUID
    project_id: UUID
    profile: TaskProfile
    task_input: Mapping[str, Any]
    is_synthetic: bool = False

    def __post_init__(self) -> None:
        """Erro de programação, não do modelo: falha já na montagem da tarefa."""
        fields = self.profile.output_schema.model_fields
        unknown = sorted(set(self.task_input) - set(fields))
        if unknown:
            raise ValueError(f"task_input tem campos fora do output_schema: {unknown}")
        if "project_id" in fields and self.task_input.get("project_id") != str(self.project_id):
            raise ValueError("task_input['project_id'] precisa ser o project_id da tarefa")


@dataclass(frozen=True, slots=True)
class MakerResult:
    status: MakerStatus
    calls: tuple[CallRecord, ...]
    attempts: int
    artifact: BaseModel | None = None
    outcome: VerificationOutcome | None = None
    artifact_event_id: UUID | None = None
    verification_event_id: UUID | None = None
    error: RunError | None = None


@dataclass
class _Conversation:
    messages: list[dict[str, Any]]
    calls: list[CallRecord] = field(default_factory=list)
    attempts: int = 1
    tool_turns: int = 0


class Maker:
    def __init__(
        self,
        *,
        client: MessagesClient,
        registry: ToolRegistry,
        policy: ToolPolicy,
        checker: DeterministicChecker,
        verifier: Verifier,
        evidence: EvidenceGateway,
        settings: ModelSettings | None = None,
    ) -> None:
        self._client = client
        self._registry = registry
        self._policy = policy
        self._checker = checker
        self._verifier = verifier
        self._evidence = evidence
        self._settings = settings if settings is not None else ModelSettings()

    async def run(self, task: MakerTask) -> MakerResult:
        conversation = _Conversation(messages=[_task_message(task.task_input)])
        system = system_blocks(load_prompt(task.profile))
        tools = tool_definitions(self._registry.specs_for(task.profile))
        while True:
            try:
                response, record = await create_message(
                    self._client,
                    self._settings,
                    prompt_version=task.profile.prompt_version,
                    system=system,
                    tools=tools,
                    messages=conversation.messages,
                )
            except MakerProviderError as exc:
                return _finish(conversation, MakerStatus.FAILED, error=exc.run_error)
            conversation.calls.append(record)
            result = await self._handle(task, conversation, response)
            if result is not None:
                return result

    async def _handle(
        self, task: MakerTask, conversation: _Conversation, response: Any
    ) -> MakerResult | None:
        """Trata uma resposta. `None` = a conversa continua (tool use ou refazer)."""
        stop = response.stop_reason
        if stop == "refusal":
            error = RunError(code="maker_refused", message="o modelo recusou", retryable=False)
            return _finish(conversation, MakerStatus.REFUSED, error=error)
        if stop == "tool_use":
            return await self._run_tools(task, conversation, response)
        if stop == "max_tokens":
            # A resposta cortada não entra no histórico (pode ter tool_use sem resultado).
            return self._redo(conversation, OutputProblem(TRUNCATED, ()), truncated_feedback())
        if stop != "end_turn":
            message = f"stop_reason inesperado: {stop}"
            error = RunError(code="maker_unexpected_stop", message=message, retryable=False)
            return _finish(conversation, MakerStatus.FAILED, error=error)
        conversation.messages.append({"role": "assistant", "content": response.content})
        return await self._handle_output(task, conversation, _text_of(response))

    async def _run_tools(
        self, task: MakerTask, conversation: _Conversation, response: Any
    ) -> MakerResult | None:
        conversation.tool_turns += 1
        if conversation.tool_turns > MAX_TOOL_TURNS:
            error = RunError(
                code="maker_tool_loop_limit", message="limite de turnos de tool", retryable=False
            )
            return _finish(conversation, MakerStatus.FAILED, error=error)
        conversation.messages.append({"role": "assistant", "content": response.content})
        context = ToolCallContext(
            tenant_id=task.tenant_id, run_id=task.run_id, profile=task.profile
        )
        results = [
            await self._tool_result(context, block)
            for block in response.content
            if block.type == "tool_use"
        ]
        conversation.messages.append({"role": "user", "content": results})
        return None

    async def _tool_result(self, context: ToolCallContext, block: Any) -> dict[str, Any]:
        # Entrada que não é objeto JSON é negada (e auditada) pela policy, sem executar.
        result = await self._policy.execute(context, str(block.name), block.input)
        return {
            "type": "tool_result",
            "tool_use_id": block.id,
            "content": result.model_dump_json(exclude_none=True),
            "is_error": result.status in {ToolCallStatus.ERROR, ToolCallStatus.DENIED},
        }

    async def _handle_output(
        self, task: MakerTask, conversation: _Conversation, text: str
    ) -> MakerResult | None:
        parsed = parse_output(text, task.profile.output_schema, task.task_input)
        if isinstance(parsed, OutputProblem):
            return self._redo(conversation, parsed, output_feedback(parsed))
        artifact: VerifiableArtifact = parsed  # type: ignore[assignment]
        try:
            evidence = await self._evidence.get_many(
                task.tenant_id, task.project_id, cited_evidence_ids(artifact)
            )
            outcome = await verify_artifact(
                artifact, evidence, checker=self._checker, verifier=self._verifier
            )
        except VerifierUnavailableError:
            error = RunError(
                code="checker_unavailable", message="Checker indisponível", retryable=True
            )
            return _finish(conversation, MakerStatus.FAILED, error=error)
        if outcome.maker_should_retry:
            # Reprovado nos checks: refaz; esgotado, nada vai ao ledger (não vira evidência).
            redo = self._redo(
                conversation, None, checks_feedback(outcome.deterministic.issues), outcome
            )
            return redo
        return await self._persist(task, conversation, artifact, outcome)

    def _redo(
        self,
        conversation: _Conversation,
        problem: OutputProblem | None,
        feedback: str,
        outcome: VerificationOutcome | None = None,
    ) -> MakerResult | None:
        if conversation.attempts > MAX_REDOS:
            code = f"maker_{problem.code}" if problem is not None else CHECKS_FAILED
            message = "saída rejeitada após o limite de tentativas"
            error = RunError(code=code, message=message, retryable=False)
            return _finish(conversation, MakerStatus.INVALID_OUTPUT, error=error, outcome=outcome)
        conversation.attempts += 1
        conversation.messages.append({"role": "user", "content": feedback})
        return None

    async def _persist(
        self,
        task: MakerTask,
        conversation: _Conversation,
        artifact: VerifiableArtifact,
        outcome: VerificationOutcome,
    ) -> MakerResult:
        model = conversation.calls[-1].model
        try:
            saved = await self._evidence.append(
                artifact_event(task, artifact, outcome, model=model, attempts=conversation.attempts)
            )
            verification = await self._evidence.append(
                verification_event(
                    tenant_id=task.tenant_id,
                    project_id=task.project_id,
                    artifact_event_id=saved.id,
                    outcome=outcome,
                    is_synthetic=task.is_synthetic,
                )
            )
        except EvidenceValidationError:
            # A transação é do chamador: quem roda o Maker (worker, #10) decide o rollback.
            error = RunError(
                code=PERSIST_FAILED, message="o ledger rejeitou o artefato", retryable=False
            )
            return _finish(conversation, MakerStatus.FAILED, error=error, outcome=outcome)
        return MakerResult(
            status=MakerStatus.COMPLETED,
            calls=tuple(conversation.calls),
            attempts=conversation.attempts,
            artifact=artifact,
            outcome=outcome,
            artifact_event_id=saved.id,
            verification_event_id=verification.id,
        )


def artifact_event(
    task: MakerTask,
    artifact: VerifiableArtifact,
    outcome: VerificationOutcome,
    *,
    model: str,
    attempts: int,
) -> NewEvidenceEvent:
    """Rascunho do Maker no ledger: `actor` = maker + modelo; versão do prompt no payload."""
    return NewEvidenceEvent(
        tenant_id=task.tenant_id,
        project_id=task.project_id,
        kind=EventKind.ACTIVITY_RECORD,
        source=EventSource.AGENT,
        source_ref=f"run:{task.run_id}",
        actor=Actor(type=ActorType.AGENT, id=MAKER_ACTOR_ID, model=model),
        payload={
            "artifact_type": type(artifact).__name__,
            "task_kind": task.profile.kind.value,
            "prompt_version": task.profile.prompt_version,
            "run_id": str(task.run_id),
            "attempts": attempts,
            "status": outcome.status.value,
            "draft": json.loads(artifact.model_dump_json()),
        },
        is_synthetic=task.is_synthetic,
    )


def _task_message(task_input: Mapping[str, Any]) -> dict[str, Any]:
    rendered = json.dumps(dict(task_input), ensure_ascii=False, sort_keys=True, indent=2)
    return {"role": "user", "content": f"Tarefa (dados do sistema):\n```json\n{rendered}\n```"}


def _text_of(response: Any) -> str:
    return "".join(block.text for block in response.content if block.type == "text")


def _finish(
    conversation: _Conversation,
    status: MakerStatus,
    *,
    error: RunError | None,
    outcome: VerificationOutcome | None = None,
) -> MakerResult:
    """Fim sem gravar no ledger. `outcome` (se houver) só para diagnóstico do run."""
    return MakerResult(
        status=status,
        calls=tuple(conversation.calls),
        attempts=conversation.attempts,
        error=error,
        outcome=outcome,
    )
