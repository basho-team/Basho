"""Fakes do Maker: cliente Anthropic roteirizado, gateway de evidências e verificador fixo.

Nenhum teste fala com a API real: as respostas são montadas aqui com o mesmo formato de
atributos do SDK (`content[].type`, `stop_reason`, `usage`, `model`).
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from basho.agent.artifacts import ResearchReportDraft
from basho.agent.ledger_tools import is_citable
from basho.agent.verifier import Verdict, VerifiableArtifact, VerificationResult
from basho.evidence.contracts import EvidenceEvent, NewEvidenceEvent
from basho.evidence.domain.hashing import compute_content_hash

FAKE_MODEL = "claude-opus-5-5"
CHECKER_MODEL = "test-checker-model"


@dataclass(frozen=True)
class TextBlock:
    text: str
    type: str = "text"


@dataclass(frozen=True)
class ThinkingBlock:
    thinking: str = ""
    signature: str = "sig"
    type: str = "thinking"


@dataclass(frozen=True)
class ToolUseBlock:
    name: str
    input: Any
    id: str = field(default_factory=lambda: f"toolu_{uuid4().hex[:12]}")
    type: str = "tool_use"


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 1200
    output_tokens: int = 300
    cache_read_input_tokens: int = 900
    cache_creation_input_tokens: int = 0


@dataclass(frozen=True)
class FakeResponse:
    content: list[Any]
    stop_reason: str
    usage: Usage = field(default_factory=Usage)
    model: str = FAKE_MODEL
    _request_id: str = "req_test"


def final(text: str) -> FakeResponse:
    return FakeResponse(content=[ThinkingBlock(), TextBlock(text)], stop_reason="end_turn")


def tool_call(name: str, arguments: Any) -> FakeResponse:
    return FakeResponse(
        content=[ThinkingBlock(), ToolUseBlock(name, arguments)], stop_reason="tool_use"
    )


class FakeMessages:
    def __init__(self, script: Sequence[FakeResponse | BaseException]) -> None:
        self._script = list(script)
        self.requests: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> FakeResponse:
        # Cópia rasa do histórico: o Maker continua anexando à mesma lista depois.
        self.requests.append({**kwargs, "messages": list(kwargs["messages"])})
        if not self._script:
            raise AssertionError("o Maker chamou o modelo mais vezes que o roteiro previa")
        step = self._script.pop(0)
        if isinstance(step, BaseException):
            raise step
        return step


class FakeClient:
    def __init__(self, script: Sequence[FakeResponse | BaseException]) -> None:
        self.messages = FakeMessages(script)


class InMemoryEvidence:
    """`EvidenceGateway` em memória: eventos conhecidos + eventos gravados pelo Maker."""

    def __init__(self, events: Sequence[EvidenceEvent] = ()) -> None:
        self._events = {event.id: event for event in events}
        self.appended: list[EvidenceEvent] = []

    async def get_many(
        self, tenant_id: UUID, project_id: UUID, ids: Sequence[UUID]
    ) -> list[EvidenceEvent]:
        return [
            self._events[i]
            for i in dict.fromkeys(ids)
            if i in self._events
            and self._events[i].tenant_id == tenant_id
            and self._events[i].project_id == project_id
            and is_citable(self._events[i])
        ]

    async def append(self, event: NewEvidenceEvent) -> EvidenceEvent:
        saved = EvidenceEvent(
            **event.model_dump(),
            id=uuid4(),
            content_hash=compute_content_hash(event),
            created_at=datetime.now(UTC),
        )
        self._events[saved.id] = saved
        self.appended.append(saved)
        return saved


class FixedVerifier:
    def __init__(self, verdict: Verdict = Verdict.PASS) -> None:
        self.model_id = CHECKER_MODEL
        self._verdict = verdict
        self.seen: list[VerifiableArtifact] = []

    async def verify(
        self, artifact: VerifiableArtifact, evidence: Sequence[EvidenceEvent]
    ) -> VerificationResult:
        self.seen.append(artifact)
        return VerificationResult(verdict=self._verdict, checker=self.model_id)


def report_input(draft: ResearchReportDraft) -> dict[str, Any]:
    """`task_input` que o sistema enviaria para produzir `draft`."""
    return {
        "project_id": str(draft.project_id),
        "researcher_id": str(draft.researcher_id),
        "period": draft.period.model_dump(mode="json"),
    }
