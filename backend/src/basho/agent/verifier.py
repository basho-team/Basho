"""Contrato do Checker (ADR-0004).

O Checker recebe apenas o artefato e as evidências citadas — nunca o raciocínio do Maker.
Provedor padrão: Featherless (API compatível com OpenAI, `base_url` configurável);
fallback: outro modelo Claude com contexto limpo.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from basho.agent.artifacts import ActivityRecordDraft
from basho.evidence.contracts import EvidenceEvent


class Verdict(StrEnum):
    PASS = "pass"
    FAIL = "fail"


class IssueSeverity(StrEnum):
    BLOCKER = "blocker"
    MAJOR = "major"
    MINOR = "minor"


class CheckIssue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str = Field(
        description="Ex.: uncited_claim, inferred_hours, prompt_injection"
    )
    message: str
    severity: IssueSeverity
    evidence_id: UUID | None = None


class UnsupportedClaim(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    claim_text: str
    reason: str


class VerificationResult(BaseModel):
    """Saída do Checker, validada por Pydantic. Também usada pelos checks determinísticos."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    verdict: Verdict
    issues: tuple[CheckIssue, ...] = ()
    unsupported_claims: tuple[UnsupportedClaim, ...] = ()
    checker: str = Field(description="'deterministic' ou id do modelo")


class DeterministicChecker(Protocol):
    """Roda antes de qualquer LLM: schema, citações existentes, sem dados formais inferidos."""

    def check(
        self, artifact: ActivityRecordDraft, evidence: Sequence[EvidenceEvent]
    ) -> VerificationResult: ...


class Verifier(Protocol):
    """Checker LLM independente."""

    model_id: str

    async def verify(
        self, artifact: ActivityRecordDraft, evidence: Sequence[EvidenceEvent]
    ) -> VerificationResult: ...
