"""Propagação de correções: ``supersedes`` → ``needs_review`` (#11, ADR-0003).

Quando um evento é corrigido (um novo evento com ``supersedes``), todo artefato
(``activity_record``: rascunho do Maker ou versão de relatório) que cita o evento substituído
vai para ``needs_review``. O mesmo acontece, transitivamente, com o que cita esse artefato. Cada
transição é um **novo** evento ``status_changed`` (actor ``system``) com a causa no payload;
nada é alterado. Resolve só com consultas ao ledger (sem tabela nova).

Garantias:
- idempotente: reprocessar a mesma correção não duplica transições (checagem + advisory lock);
- sem ciclos: cada artefato é visitado uma vez por propagação;
- artefato já substituído por versão nova não é marcado (a versão nova é que vale).

A transação pertence ao chamador (``tenant_session``), como no ``EvidenceService``: a correção
e a propagação podem ser gravadas juntas.
"""

from collections import deque
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from basho.evidence.contracts import (
    Actor,
    ActorType,
    ArtifactStatus,
    EventKind,
    EventSource,
    EvidenceEvent,
    NewEvidenceEvent,
)
from basho.evidence.domain.rules import EvidenceValidationError
from basho.evidence.propagation_repository import PropagationRepository
from basho.evidence.service import EvidenceService

PROPAGATION_ACTOR = Actor(type=ActorType.SYSTEM, id="propagation")
MAX_DEPTH = 10
"""Limite de saltos transitivos (defesa contra grafos patológicos; o normal é 1 a 2)."""
REASON_EVIDENCE_SUPERSEDED = "evidence_superseded"
REASON_REOPENED = "reopened_for_maker"


class ReviewMark(BaseModel):
    """Um artefato levado a ``needs_review`` por esta propagação."""

    model_config = ConfigDict(frozen=True)

    artifact_event_id: UUID
    status_event_id: UUID
    via_event_id: UUID
    depth: int


class PropagationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    correction_event_id: UUID
    superseded_event_id: UUID
    marked: tuple[ReviewMark, ...]
    already_marked: tuple[UUID, ...]


class PendingReview(BaseModel):
    """Artefato cujo status atual é ``needs_review`` (para pendências, #5, e worker, #10)."""

    model_config = ConfigDict(frozen=True)

    artifact_event_id: UUID
    status_event_id: UUID
    cause_event_id: UUID
    superseded_event_id: UUID
    marked_at: datetime


def _status_event(
    artifact: EvidenceEvent, status: ArtifactStatus, payload: dict[str, object]
) -> NewEvidenceEvent:
    return NewEvidenceEvent(
        tenant_id=artifact.tenant_id,
        project_id=artifact.project_id,
        kind=EventKind.STATUS_CHANGED,
        source=EventSource.SYSTEM,
        source_ref=f"artifact:{artifact.id}",
        actor=PROPAGATION_ACTOR,
        payload={"artifact_event_id": str(artifact.id), "status": status.value, **payload},
        is_synthetic=artifact.is_synthetic,
    )


class CorrectionPropagation:
    """Serviço público da propagação (usa só o ``EvidenceService`` para gravar e ler)."""

    def __init__(self, session: AsyncSession) -> None:
        self._evidence = EvidenceService(session)
        self._repository = PropagationRepository(session)

    async def propagate(self, tenant_id: UUID, correction_event_id: UUID) -> PropagationResult:
        """Marca ``needs_review`` em tudo que depende do evento substituído pela correção."""
        correction = await self._evidence.get(tenant_id, correction_event_id)
        if correction.supersedes is None:
            raise EvidenceValidationError("evento não é correção: não tem supersedes")
        await self._repository.lock(f"propagation:{tenant_id}:{correction.id}")
        marked: list[ReviewMark] = []
        already: list[UUID] = []
        visited: set[UUID] = {correction.supersedes, correction.id}
        frontier: deque[tuple[UUID, int]] = deque([(correction.supersedes, 1)])
        while frontier:
            cited_id, depth = frontier.popleft()
            if depth > MAX_DEPTH:
                continue
            for artifact_id in await self._repository.citing_artifacts(
                tenant_id, correction.project_id, cited_id
            ):
                if artifact_id in visited:
                    continue
                visited.add(artifact_id)
                mark = await self._mark(correction, artifact_id, cited_id, depth)
                if mark is None:
                    already.append(artifact_id)
                else:
                    marked.append(mark)
                frontier.append((artifact_id, depth + 1))
        return PropagationResult(
            correction_event_id=correction.id,
            superseded_event_id=correction.supersedes,
            marked=tuple(marked),
            already_marked=tuple(already),
        )

    async def _mark(
        self, correction: EvidenceEvent, artifact_id: UUID, via_id: UUID, depth: int
    ) -> ReviewMark | None:
        key = {
            "artifact_event_id": str(artifact_id),
            "status": ArtifactStatus.NEEDS_REVIEW.value,
            "cause_event_id": str(correction.id),
        }
        if await self._repository.has_mark(correction.tenant_id, correction.project_id, key):
            return None
        artifact = await self._evidence.get(correction.tenant_id, artifact_id)
        saved = await self._evidence.append(
            _status_event(
                artifact,
                ArtifactStatus.NEEDS_REVIEW,
                {
                    "reason": REASON_EVIDENCE_SUPERSEDED,
                    "cause_event_id": str(correction.id),
                    "superseded_event_id": str(correction.supersedes),
                    "via_event_id": str(via_id),
                    "depth": depth,
                },
            )
        )
        return ReviewMark(
            artifact_event_id=artifact_id,
            status_event_id=saved.id,
            via_event_id=via_id,
            depth=depth,
        )

    async def pending_reviews(self, tenant_id: UUID, project_id: UUID) -> list[PendingReview]:
        """Artefatos do projeto cujo status atual é ``needs_review``, do mais antigo ao novo."""
        await self._evidence.require_session_tenant(tenant_id)
        return [
            PendingReview(
                artifact_event_id=UUID(str(payload["artifact_event_id"])),
                status_event_id=status_id,
                cause_event_id=UUID(str(payload["cause_event_id"])),
                superseded_event_id=UUID(str(payload["superseded_event_id"])),
                marked_at=marked_at,
            )
            for status_id, payload, marked_at in await self._repository.pending(
                tenant_id, project_id
            )
        ]

    async def reopen_as_draft(self, tenant_id: UUID, artifact_event_id: UUID) -> EvidenceEvent:
        """``needs_review → draft``: o worker (#10) reabre o ciclo Maker-Checker do artefato.

        Só vale a partir de ``needs_review``; outras transições (aprovar, rejeitar) são humanas
        e não passam por aqui (ADR-0005).
        """
        artifact = await self._evidence.get(tenant_id, artifact_event_id)
        if artifact.kind is not EventKind.ACTIVITY_RECORD:
            raise EvidenceValidationError("só artefatos (activity_record) são reabertos")
        latest = await self._repository.latest_status(tenant_id, artifact_event_id)
        if latest is None or latest[1].get("status") != ArtifactStatus.NEEDS_REVIEW.value:
            raise EvidenceValidationError("artefato não está em needs_review")
        status_id, payload = latest
        return await self._evidence.append(
            _status_event(
                artifact,
                ArtifactStatus.DRAFT,
                {
                    "reason": REASON_REOPENED,
                    "cause_event_id": str(payload["cause_event_id"]),
                    "superseded_event_id": str(payload["superseded_event_id"]),
                    "previous_status_event_id": str(status_id),
                },
            )
        )


__all__ = [
    "MAX_DEPTH",
    "CorrectionPropagation",
    "PendingReview",
    "PropagationResult",
    "ReviewMark",
]
