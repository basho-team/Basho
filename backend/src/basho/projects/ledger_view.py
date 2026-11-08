"""Leitura derivada do ledger de um projeto: artefatos, vereditos, correções e estado (puro).

Sem banco: recebe os eventos já carregados e as decisões formais, e devolve o estado de cada
artefato e as pendências que os vereditos abrem. Regras em docs/contracts.md §5 (#5).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from basho.agent.artifacts import MissingInformation
from basho.agent.verifier import VerificationResult
from basho.compliance.api_contracts import ApprovalDecision, PendingKind
from basho.evidence.contracts import ArtifactStatus, EventKind, EventSource, EvidenceEvent

ARTIFACT_TYPE_KEY = "artifact_type"
DECISION_KINDS = frozenset({EventKind.USER_CONFIRMATION, EventKind.STATUS_CHANGED})
VIEW_KINDS = (
    EventKind.ACTIVITY_RECORD,
    EventKind.VERIFICATION_RESULT,
    EventKind.USER_CORRECTION,
    *sorted(DECISION_KINDS),
)
PENDING_STATUSES = frozenset({ArtifactStatus.NEEDS_HUMAN, ArtifactStatus.VERIFIED})
DEFAULT_REPORT_TITLE = "Relatório do pesquisador"
DEFAULT_TITLE = "Registro de atividade"
CHECKER_QUESTION = (
    "O Checker discordou do rascunho. Revise as divergências e responda com a correção "
    "ou a confirmação do que está registrado."
)
APPROVAL_QUESTION = "Registro verificado pelo Checker. Aprovar ou rejeitar é ação formal do gestor."
CHECKER_KEY = "checker"
APPROVAL_KEY = "approval"
MISSING_KEY_PREFIX = "missing:"


@dataclass(frozen=True)
class PendingSpec:
    """Pendência que um veredito abre (antes de virar linha em `pending_items`)."""

    source_key: str
    kind: PendingKind
    title: str
    question: str
    assignee_role: str
    activity_id: UUID | None


@dataclass
class ArtifactView:
    event: EvidenceEvent
    verifications: list[EvidenceEvent] = field(default_factory=list)
    corrections: list[EvidenceEvent] = field(default_factory=list)
    decisions: list[EvidenceEvent] = field(default_factory=list)

    @property
    def draft(self) -> dict[str, Any]:
        draft = self.event.payload.get("draft")
        return draft if isinstance(draft, dict) else {}

    @property
    def title(self) -> str:
        title = self.draft.get("title")
        if isinstance(title, str) and title.strip():
            return title
        if self.event.payload.get(ARTIFACT_TYPE_KEY) == "ResearchReportDraft":
            return DEFAULT_REPORT_TITLE
        return DEFAULT_TITLE

    @property
    def activity_id(self) -> UUID | None:
        return _uuid_or_none(self.draft.get("activity_id"))

    @property
    def run_id(self) -> UUID | None:
        return _uuid_or_none(self.event.payload.get("run_id"))

    @property
    def latest_verification(self) -> EvidenceEvent | None:
        return self.verifications[-1] if self.verifications else None

    def status(self, decision: ApprovalDecision | None) -> ArtifactStatus:
        if decision is ApprovalDecision.APPROVE:
            return ArtifactStatus.APPROVED
        if decision is ApprovalDecision.REJECT:
            return ArtifactStatus.REJECTED
        if self.corrections:  # humano corrigiu: o Maker refaz (needs_human → draft, ADR-0004)
            return ArtifactStatus.DRAFT
        latest = self.latest_verification
        if latest is None:
            return ArtifactStatus.PROPOSED
        try:
            return ArtifactStatus(str(latest.payload.get("status")))
        except ValueError:
            return ArtifactStatus.PROPOSED

    def cited_evidence_ids(self) -> set[UUID]:
        cited: set[UUID] = set()
        for claim in self.draft.get("claims") or ():
            if isinstance(claim, dict):
                cited.update(_uuids(claim.get("evidence_ids")))
        cited.update(_uuids(self.draft.get("formal_hours_event_ids")))
        return cited

    def verification_results(self) -> list[VerificationResult]:
        results: list[VerificationResult] = []
        for event in self.verifications:
            for key in ("deterministic", "checker"):
                raw = event.payload.get(key)
                if raw is None:
                    continue
                try:
                    results.append(VerificationResult.model_validate(raw))
                except ValidationError:
                    continue  # veredito malformado não derruba o dossiê
        return results

    def history(self) -> list[EvidenceEvent]:
        # Eventos da mesma transação têm o mesmo created_at (now()): desempata pela ordem lógica.
        groups = (
            [self.event],
            self.verifications,
            self.corrections,
            self.decisions,
        )
        ranked = [
            (event.created_at, rank, event) for rank, group in enumerate(groups) for event in group
        ]
        return [event for _, _, event in sorted(ranked, key=lambda item: (item[0], item[1]))]

    def pending_specs(self) -> list[PendingSpec]:
        """Pendências que o veredito mais recente abre (vazio se não for needs_human/verified)."""
        latest = self.latest_verification
        if latest is None or latest.payload.get("status") not in PENDING_STATUSES:
            return []
        specs: list[PendingSpec] = []
        if latest.payload["status"] == ArtifactStatus.NEEDS_HUMAN:
            specs.append(
                self._spec(
                    CHECKER_KEY, PendingKind.CHECKER_DISAGREEMENT, CHECKER_QUESTION, "researcher"
                )
            )
        else:
            specs.append(
                self._spec(
                    APPROVAL_KEY, PendingKind.APPROVAL_REQUIRED, APPROVAL_QUESTION, "manager"
                )
            )
        for index, raw in enumerate(self.draft.get("missing") or ()):
            try:
                missing = MissingInformation.model_validate(raw)
            except ValidationError:
                continue
            specs.append(
                self._spec(
                    f"{MISSING_KEY_PREFIX}{index}",
                    PendingKind.MISSING_JUSTIFICATION,
                    missing.question,
                    missing.ask_role,
                )
            )
        return specs

    def _spec(self, key: str, kind: PendingKind, question: str, role: str) -> PendingSpec:
        return PendingSpec(key, kind, self.title, question, role, self.activity_id)


def build_artifacts(events: Iterable[EvidenceEvent]) -> dict[UUID, ArtifactView]:
    """Agrupa os eventos do projeto por artefato do Maker (`payload.artifact_type`)."""
    ordered = sorted(events, key=lambda event: (event.created_at, str(event.id)))
    artifacts = {
        event.id: ArtifactView(event)
        for event in ordered
        if event.kind is EventKind.ACTIVITY_RECORD
        and event.source is EventSource.AGENT
        and ARTIFACT_TYPE_KEY in event.payload
    }
    for event in ordered:
        if event.kind is EventKind.VERIFICATION_RESULT:
            target = _uuid_or_none(event.payload.get("artifact_event_id"))
            if target in artifacts:
                artifacts[target].verifications.append(event)
        elif event.kind is EventKind.USER_CORRECTION and event.supersedes in artifacts:
            artifacts[event.supersedes].corrections.append(event)
        elif event.kind in DECISION_KINDS and event.source is EventSource.USER:
            target = _uuid_or_none(event.payload.get("artifact_event_id"))
            if target in artifacts:
                artifacts[target].decisions.append(event)
    return artifacts


def decision_of(decisions: Mapping[UUID, str], artifact_id: UUID) -> ApprovalDecision | None:
    raw = decisions.get(artifact_id)
    return None if raw is None else ApprovalDecision(raw)


def _uuid_or_none(value: object) -> UUID | None:
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        try:
            return UUID(value)
        except ValueError:
            return None
    return None


def _uuids(values: object) -> set[UUID]:
    if not isinstance(values, list | tuple):
        return set()
    return {parsed for value in values if (parsed := _uuid_or_none(value)) is not None}
