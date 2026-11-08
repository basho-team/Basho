"""Checker independente e orquestração da verificação (ADR-0004, issue #9).

O Checker vê **só** o artefato e as evidências citadas por ele, nunca o raciocínio do
Maker. Provedor padrão: API compatível com OpenAI (Featherless); fallback: outro modelo
Claude com contexto limpo. Toda resposta do modelo é validada por Pydantic; resposta
inválida vira `fail`, nunca aprovação silenciosa.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

import anthropic
import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError

from basho.agent.checks import cited_evidence_ids, contains_injection
from basho.agent.verifier import (
    CheckIssue,
    DeterministicChecker,
    IssueSeverity,
    UnsupportedClaim,
    Verdict,
    VerifiableArtifact,
    VerificationResult,
    Verifier,
)
from basho.evidence.contracts import (
    FORMAL_DATA_KINDS,
    Actor,
    ActorType,
    ArtifactStatus,
    EventKind,
    EventSource,
    EvidenceEvent,
    NewEvidenceEvent,
)

CHECKER_PROMPT_VERSION = "v1"
CHECKER_PROMPT_PATH = Path(__file__).parent / "prompts" / "checker" / f"{CHECKER_PROMPT_VERSION}.md"
DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_CLAUDE_CHECKER_MODEL = "claude-sonnet-5-5"
"""Fallback: modelo Claude diferente do Maker, com contexto limpo."""
CLAUDE_MAX_TOKENS = 16000
INVALID_RESPONSE = "checker_invalid_response"
REFUSED = "checker_refused"
TRUNCATED = "checker_truncated"
INCONSISTENT_VERDICT = "checker_inconsistent_verdict"
REDACTED_KINDS: frozenset[EventKind] = FORMAL_DATA_KINDS
"""Payload formal (horas, dispêndio: pessoas e valores) não vai ao provedor externo (LGPD):
só tipo e origem. Mesma fonte que o Maker usa (`FORMAL_DATA_KINDS`)."""
_BLOCKING_SEVERITIES = frozenset({IssueSeverity.BLOCKER, IssueSeverity.MAJOR})
_ENVELOPE_ESCAPES = {"<": r"\u003c", ">": r"\u003e", "&": r"\u0026"}

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class VerifierUnavailableError(RuntimeError):
    """Provedor fora do ar, sem chave, com timeout ou erro HTTP: cabe fallback."""


def _escape_envelope(body: str) -> str:
    """Impede que o conteúdo feche `<evidence>`: escapa `< > &` como unicode JSON."""
    for char, escaped in _ENVELOPE_ESCAPES.items():
        body = body.replace(char, escaped)
    return body


def _evidence_body(event: EvidenceEvent) -> str:
    payload: Any = (
        "[omitido: dado formal, conferido pelos checks determinísticos]"
        if event.kind in REDACTED_KINDS
        else event.payload
    )
    data = {
        "kind": event.kind.value,
        "source": event.source.value,
        "source_ref": event.source_ref,
        "payload": payload,
    }
    return _escape_envelope(json.dumps(data, ensure_ascii=False, sort_keys=True))


def load_checker_prompt() -> str:
    return CHECKER_PROMPT_PATH.read_text(encoding="utf-8")


def build_checker_input(artifact: VerifiableArtifact, evidence: Sequence[EvidenceEvent]) -> str:
    """Mensagem do Checker: artefato + **só** as evidências citadas, como dado não confiável.

    A assinatura não aceita raciocínio, histórico nem prompt do Maker: isso é deliberado.
    """
    by_id = {event.id: event for event in evidence}
    blocks = []
    for evidence_id in cited_evidence_ids(artifact):
        event = by_id.get(evidence_id)
        if event is None:
            blocks.append(f'<evidence id="{evidence_id}" missing="true" />')
            continue
        flag = ' suspicious_instructions="true"' if contains_injection(event) else ""
        body = _evidence_body(event)
        header = f'<evidence id="{evidence_id}" untrusted="true"{flag}>'
        blocks.append(f"{header}\n{body}\n</evidence>")
    artifact_json = _escape_envelope(artifact.model_dump_json(indent=1))
    return (
        "<artifact>\n" + artifact_json + "\n</artifact>\n\n"
        "<evidence_set>\n" + "\n".join(blocks) + "\n</evidence_set>"
    )


class _CheckerReply(BaseModel):
    """Formato pedido ao modelo; campos extras são ignorados, os pedidos são validados."""

    model_config = ConfigDict(extra="ignore")

    verdict: Verdict
    issues: list[CheckIssue] = Field(default_factory=list)
    unsupported_claims: list[UnsupportedClaim] = Field(default_factory=list)


def parse_checker_reply(text: str, model_id: str) -> VerificationResult:
    """Converte a resposta do modelo; qualquer coisa inválida vira `fail` com issue."""
    try:
        reply = _CheckerReply.model_validate(json.loads(_FENCE.sub("", text.strip())))
    except (json.JSONDecodeError, ValidationError):
        return _invalid(model_id, "resposta do Checker não é o JSON esperado")
    issues = list(reply.issues)
    verdict = reply.verdict
    blocking = any(issue.severity in _BLOCKING_SEVERITIES for issue in issues)
    if verdict is Verdict.PASS and (blocking or reply.unsupported_claims):
        verdict = Verdict.FAIL
        issues.append(
            CheckIssue(
                code=INCONSISTENT_VERDICT,
                message="pass com issue blocker/major ou afirmação sem sustentação",
                severity=IssueSeverity.MAJOR,
            )
        )
    return VerificationResult(
        verdict=verdict,
        issues=tuple(issues),
        unsupported_claims=tuple(reply.unsupported_claims),
        checker=model_id,
    )


def _invalid(model_id: str, message: str, code: str = INVALID_RESPONSE) -> VerificationResult:
    issue = CheckIssue(code=code, message=message, severity=IssueSeverity.MAJOR)
    return VerificationResult(verdict=Verdict.FAIL, issues=(issue,), checker=model_id)


class OpenAICompatibleVerifier:
    """Checker via API compatível com OpenAI (Featherless por padrão; troca só por config)."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: SecretStr | None,
        model_id: str,
        http_client: httpx.AsyncClient | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.model_id = model_id
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._api_key = api_key
        self._client = http_client
        self._timeout = timeout

    async def verify(
        self, artifact: VerifiableArtifact, evidence: Sequence[EvidenceEvent]
    ) -> VerificationResult:
        if self._api_key is None or not self._api_key.get_secret_value():
            raise VerifierUnavailableError("provedor do Checker sem chave configurada")
        body = {
            "model": self.model_id,
            "messages": [
                {"role": "system", "content": load_checker_prompt()},
                {"role": "user", "content": build_checker_input(artifact, evidence)},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        headers = {"Authorization": f"Bearer {self._api_key.get_secret_value()}"}
        try:
            if self._client is not None:
                response = await self._client.post(
                    self._url, json=body, headers=headers, timeout=self._timeout
                )
            else:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        self._url, json=body, headers=headers, timeout=self._timeout
                    )
            response.raise_for_status()
            choice = response.json()["choices"][0]
            content = choice["message"]["content"]
        except httpx.HTTPStatusError as exc:
            raise VerifierUnavailableError(
                f"provedor do Checker respondeu HTTP {exc.response.status_code}"
            ) from None
        except httpx.HTTPError as exc:
            raise VerifierUnavailableError(
                f"falha de rede no provedor do Checker: {type(exc).__name__}"
            ) from None
        except (KeyError, IndexError, TypeError, ValueError):
            return _invalid(self.model_id, "resposta do provedor sem choices[0].message.content")
        if choice.get("finish_reason") == "length":
            return _invalid(self.model_id, "resposta do Checker truncada", TRUNCATED)
        return parse_checker_reply(str(content), self.model_id)


class _AnthropicLike(Protocol):
    """O suficiente de `anthropic.AsyncAnthropic` para o Checker (facilita o mock)."""

    @property
    def messages(self) -> Any: ...


class ClaudeVerifier:
    """Fallback: Claude com contexto limpo (só system do Checker + artefato + evidências)."""

    def __init__(
        self,
        *,
        client: _AnthropicLike,
        maker_model: str,
        model_id: str = DEFAULT_CLAUDE_CHECKER_MODEL,
    ) -> None:
        if model_id == maker_model:
            msg = f"Checker precisa de modelo diferente do Maker ({maker_model!r}), ADR-0004"
            raise ValueError(msg)
        self.model_id = model_id
        self._client = client

    async def verify(
        self, artifact: VerifiableArtifact, evidence: Sequence[EvidenceEvent]
    ) -> VerificationResult:
        try:
            response = await self._client.messages.create(
                model=self.model_id,
                max_tokens=CLAUDE_MAX_TOKENS,
                system=load_checker_prompt(),
                messages=[{"role": "user", "content": build_checker_input(artifact, evidence)}],
            )
        except anthropic.APITimeoutError:
            raise VerifierUnavailableError("timeout no Claude (Checker)") from None
        except anthropic.APIConnectionError:
            raise VerifierUnavailableError("falha de conexão com o Claude (Checker)") from None
        except anthropic.APIStatusError as exc:
            raise VerifierUnavailableError(
                f"Claude (Checker) respondeu HTTP {exc.status_code}"
            ) from None
        if response.stop_reason == "max_tokens":
            return _invalid(self.model_id, "resposta do Checker truncada", TRUNCATED)
        if response.stop_reason == "refusal":
            return _invalid(self.model_id, "o modelo recusou a verificação", REFUSED)
        text = "".join(block.text for block in response.content if block.type == "text")
        return parse_checker_reply(text, self.model_id)


class FallbackVerifier:
    """Usa o primário; se ele estiver indisponível, o secundário. Erro do secundário sobe."""

    def __init__(self, primary: Verifier, fallback: Verifier) -> None:
        self._primary = primary
        self._fallback = fallback
        self.model_id = primary.model_id

    async def verify(
        self, artifact: VerifiableArtifact, evidence: Sequence[EvidenceEvent]
    ) -> VerificationResult:
        try:
            return await self._primary.verify(artifact, evidence)
        except VerifierUnavailableError:
            return await self._fallback.verify(artifact, evidence)


@dataclass(frozen=True)
class VerificationOutcome:
    """Resultado da cadeia checks → Checker e o estado em que o artefato fica."""

    status: ArtifactStatus
    deterministic: VerificationResult
    checker: VerificationResult | None = None

    @property
    def maker_should_retry(self) -> bool:
        """Falha determinística: o Maker refaz (o orquestrador limita a 2 tentativas)."""
        return self.status is ArtifactStatus.DRAFT


async def verify_artifact(
    artifact: VerifiableArtifact,
    evidence: Sequence[EvidenceEvent],
    *,
    checker: DeterministicChecker,
    verifier: Verifier,
) -> VerificationOutcome:
    """`draft` (checks falharam) · `verified` (Checker pass) · `needs_human` (Checker discorda)."""
    deterministic = checker.check(artifact, evidence)
    if deterministic.verdict is Verdict.FAIL:
        return VerificationOutcome(ArtifactStatus.DRAFT, deterministic)
    result = await verifier.verify(artifact, evidence)
    status = (
        ArtifactStatus.VERIFIED if result.verdict is Verdict.PASS else ArtifactStatus.NEEDS_HUMAN
    )
    return VerificationOutcome(status, deterministic, result)


def verification_event(
    *,
    tenant_id: UUID,
    project_id: UUID,
    artifact_event_id: UUID,
    outcome: VerificationOutcome,
    is_synthetic: bool = False,
) -> NewEvidenceEvent:
    """Evento `VERIFICATION_RESULT` do Checker, com o modelo usado (ADR-0004)."""
    final = outcome.checker or outcome.deterministic
    return NewEvidenceEvent(
        tenant_id=tenant_id,
        project_id=project_id,
        kind=EventKind.VERIFICATION_RESULT,
        source=EventSource.AGENT,
        source_ref=f"artifact:{artifact_event_id}",
        actor=Actor(type=ActorType.AGENT, id="checker", model=final.checker),
        payload={
            "artifact_event_id": str(artifact_event_id),
            "status": outcome.status.value,
            "prompt_version": CHECKER_PROMPT_VERSION,
            "deterministic": json.loads(outcome.deterministic.model_dump_json()),
            "checker": json.loads(outcome.checker.model_dump_json()) if outcome.checker else None,
        },
        is_synthetic=is_synthetic,
    )
