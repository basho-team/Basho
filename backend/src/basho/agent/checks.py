"""Checks determinísticos de artefatos formais (ADR-0004, issue #9).

Rodam antes de qualquer LLM e não dependem de banco: recebem o artefato e as evidências
que o orquestrador carregou do ledger **do mesmo tenant**. Os códigos de issue seguem o
vocabulário dos eval cases do domínio de relatórios (PR #43).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from basho.agent.artifacts import ActivityRecordDraft, Claim, ReportClaim, ResearchReportDraft
from basho.agent.verifier import (
    CheckIssue,
    IssueSeverity,
    Verdict,
    VerifiableArtifact,
    VerificationResult,
)
from basho.evidence.contracts import FORMAL_DATA_SOURCES, EventKind, EvidenceEvent

CHECKER_ID = "deterministic"

UNKNOWN_EVIDENCE = "unknown_evidence"
FORMAL_HOURS_NOT_FORMAL = "formal_hours_not_formal"
FORMAL_DATA_IN_TEXT = "formal_data_in_text"
ELIGIBILITY_ASSERTION = "eligibility_assertion"
PROMPT_INJECTION = "prompt_injection"

FAILING_SEVERITIES: frozenset[IssueSeverity] = frozenset(
    {IssueSeverity.BLOCKER, IssueSeverity.MAJOR}
)

_HOURS = re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:h|hs|hrs?|horas?)\b", re.IGNORECASE)
_MONEY = re.compile(r"R\$\s*\d|\b\d+(?:[.,]\d+)*\s*(?:mil\s+)?reais\b", re.IGNORECASE)
_ELIGIBILITY = re.compile(
    r"\b(?:eleg[ií]ve(?:l|is)|inelig[ií]ve(?:l|is)|enquadrad[oa]s?|enquadramento|"
    r"fazem?\s+jus|qualifica-se|benef[ií]cio\s+(?:fiscal\s+)?garantido)\b",
    re.IGNORECASE,
)
_INJECTION = re.compile(
    r"(?:ignor(?:e|ar|em)|desconsider(?:e|ar|em)|esque[cç](?:a|am|er)|disregard|forget)\s+(?:as\s+|todas\s+as\s+|all\s+|the\s+)?"
    r"(?:\w+\s+)?(?:instru[cç][oõ]es|instructions|regras|orienta[cç][oõ]es|rules)"
    r"|system\s+prompt|voc[eê]\s+agora\s+[eé]|you\s+are\s+now"
    r"|(?:marque|aprove)m?\s+todas"
    r"|marque(?:m)?\s+(?:est[ea]s?|ess[ea]s?|[oa]s?)\s+(?:\w+\s+){0,3}como\s+"
    r"(?:aprovad[oa]s?|eleg[ií]ve(?:l|is)|qualificad[oa]s?)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class _Citation:
    where: str
    evidence_id: UUID


def _claims(artifact: VerifiableArtifact) -> Sequence[Claim | ReportClaim]:
    return artifact.claims


def cited_evidence_ids(artifact: VerifiableArtifact) -> list[UUID]:
    """Todas as evidências citadas pelo artefato, sem repetição e na ordem de citação."""
    return list(dict.fromkeys(citation.evidence_id for citation in _citations(artifact)))


def _report_texts(artifact: VerifiableArtifact) -> Iterator[tuple[str, str]]:
    """Textos redigidos pelo Maker (onde dados formais e enquadramento não podem aparecer).

    `eligibility_note` fica de fora: é fixa e validada pelo schema.
    """
    yield "summary", artifact.summary
    if isinstance(artifact, ActivityRecordDraft):
        yield "title", artifact.title
    for index, claim in enumerate(_claims(artifact)):
        yield f"claims[{index}].text", claim.text
    if isinstance(artifact, ResearchReportDraft):
        for index, experiment in enumerate(artifact.experiments):
            yield f"experiments[{index}].description", experiment.description
    for index, gap in enumerate(artifact.missing):
        yield f"missing[{index}].question", gap.question


def _citations(artifact: VerifiableArtifact) -> Iterator[_Citation]:
    for index, claim in enumerate(_claims(artifact)):
        for evidence_id in claim.evidence_ids:
            yield _Citation(f"claims[{index}]", evidence_id)
    if isinstance(artifact, ResearchReportDraft):
        for index, experiment in enumerate(artifact.experiments):
            for evidence_id in experiment.evidence_ids:
                yield _Citation(f"experiments[{index}]", evidence_id)
    for evidence_id in artifact.formal_hours_event_ids:
        yield _Citation("formal_hours_event_ids", evidence_id)


def _strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list | tuple):
        for item in value:
            yield from _strings(item)


_INVISIBLE = dict.fromkeys(map(ord, "\u00ad\u200b\u200c\u200d\u2060\ufeff"))
_CONFUSABLES = str.maketrans(
    "\u0430\u0435\u043e\u0440\u0441\u0445\u0443\u0456\u0410\u0415\u041e\u0420\u0421\u0425\u0406",
    "aeopcxyiAEOPCXI",
)
"""Cirílico comum que se passa por latino; o NFKC não o converte."""


def normalize_for_checks(text: str) -> str:
    """NFKC, sem caracteres invisíveis e sem homóglifos cirílicos comuns."""
    return unicodedata.normalize("NFKC", text).translate(_INVISIBLE).translate(_CONFUSABLES)


def contains_injection(event: EvidenceEvent) -> bool:
    """Heurística para instrução embutida em conteúdo externo (o conteúdo segue sendo dado)."""
    return any(_INJECTION.search(normalize_for_checks(text)) for text in _strings(event.payload))


def _issue(
    code: str, message: str, severity: IssueSeverity, evidence_id: UUID | None = None
) -> CheckIssue:
    return CheckIssue(code=code, message=message, severity=severity, evidence_id=evidence_id)


class ReportDeterministicChecker:
    """Implementa `DeterministicChecker` para os artefatos formais do Maker."""

    def __init__(self, tenant_id: UUID) -> None:
        self._tenant_id = tenant_id

    def check(
        self, artifact: VerifiableArtifact, evidence: Sequence[EvidenceEvent]
    ) -> VerificationResult:
        known = {event.id: event for event in evidence if event.tenant_id == self._tenant_id}
        issues = [
            *self._unknown_evidence(artifact, known),
            *self._formal_hours(artifact, known),
            *self._text_rules(artifact),
            *self._injection(artifact, known),
        ]
        failed = any(issue.severity in FAILING_SEVERITIES for issue in issues)
        return VerificationResult(
            verdict=Verdict.FAIL if failed else Verdict.PASS,
            issues=tuple(issues),
            checker=CHECKER_ID,
        )

    @staticmethod
    def _unknown_evidence(
        artifact: VerifiableArtifact, known: dict[UUID, EvidenceEvent]
    ) -> Iterable[CheckIssue]:
        reported: set[UUID] = set()
        for citation in _citations(artifact):
            if citation.evidence_id in known or citation.evidence_id in reported:
                continue
            reported.add(citation.evidence_id)
            yield _issue(
                UNKNOWN_EVIDENCE,
                f"{citation.where} cita evidência inexistente neste tenant",
                IssueSeverity.BLOCKER,
                citation.evidence_id,
            )

    @staticmethod
    def _formal_hours(
        artifact: VerifiableArtifact, known: dict[UUID, EvidenceEvent]
    ) -> Iterable[CheckIssue]:
        for evidence_id in artifact.formal_hours_event_ids:
            event = known.get(evidence_id)
            if event is None:
                continue  # já reportado como unknown_evidence
            if (
                event.kind is not EventKind.FORMAL_HOURS_DECLARED
                or event.source not in FORMAL_DATA_SOURCES
            ):
                yield _issue(
                    FORMAL_HOURS_NOT_FORMAL,
                    "formal_hours_event_ids deve apontar para FORMAL_HOURS_DECLARED "
                    "de origem humana ou formal",
                    IssueSeverity.BLOCKER,
                    evidence_id,
                )

    @staticmethod
    def _text_rules(artifact: VerifiableArtifact) -> Iterable[CheckIssue]:
        for where, text in _report_texts(artifact):
            if _HOURS.search(text) or _MONEY.search(text):
                yield _issue(
                    FORMAL_DATA_IN_TEXT,
                    f"{where} escreve horas ou valores; use referência a evento formal",
                    IssueSeverity.MAJOR,
                )
            if _ELIGIBILITY.search(text):
                yield _issue(
                    ELIGIBILITY_ASSERTION,
                    f"{where} afirma enquadramento ou elegibilidade; isso é decisão humana",
                    IssueSeverity.BLOCKER,
                )

    @staticmethod
    def _injection(
        artifact: VerifiableArtifact, known: dict[UUID, EvidenceEvent]
    ) -> Iterable[CheckIssue]:
        cited = {citation.evidence_id for citation in _citations(artifact)}
        for evidence_id in sorted(cited & known.keys(), key=str):
            if contains_injection(known[evidence_id]):
                yield _issue(
                    PROMPT_INJECTION,
                    "evidência citada contém instrução embutida; conferir se o texto não a seguiu",
                    IssueSeverity.MAJOR,
                    evidence_id,
                )
