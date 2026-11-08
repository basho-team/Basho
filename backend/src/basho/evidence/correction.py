"""Correção humana de uma evidência: novo evento com `supersedes` + propagação (#11).

O evento original nunca muda (ADR-0003). A correção repete o tipo e a origem semântica do
original com a descrição corrigida e o motivo, e na mesma transação leva a `needs_review` tudo
o que citava a evidência (versões de relatório inclusive). Dados formais (horas, despesas) não
são corrigíveis por aqui: exigem novo registro formal.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from basho.evidence.contracts import (
    FORMAL_DATA_KINDS,
    Actor,
    ActorType,
    EventSource,
    NewEvidenceEvent,
)
from basho.evidence.domain.rules import EvidenceValidationError
from basho.evidence.propagation import CorrectionPropagation, PropagationResult
from basho.evidence.service import EvidenceService


class EvidenceCorrectionService:
    def __init__(self, session: AsyncSession) -> None:
        self._ledger = EvidenceService(session)
        self._propagation = CorrectionPropagation(session)

    async def correct(
        self,
        tenant_id: UUID,
        project_id: UUID,
        event_id: UUID,
        *,
        description: str,
        reason: str,
        author_id: UUID,
        author_role: str,
    ) -> PropagationResult:
        original = await self._ledger.get(tenant_id, event_id)
        if original.project_id != project_id:
            raise EvidenceValidationError("evidência de outro projeto")
        if original.kind in FORMAL_DATA_KINDS:
            raise EvidenceValidationError("dado formal só se corrige com novo registro formal")
        payload: dict[str, Any] = {
            **original.payload,
            "description": description,
            "correction_reason": reason,
            "corrected_by_role": author_role,
            "identity_verified": False,  # placeholder de identidade até #47
        }
        correction = await self._ledger.append(
            NewEvidenceEvent(
                tenant_id=tenant_id,
                project_id=project_id,
                kind=original.kind,
                source=EventSource.USER,
                source_ref=original.source_ref,
                actor=Actor(type=ActorType.USER, id=str(author_id)),
                payload=payload,
                supersedes=original.id,
                is_synthetic=original.is_synthetic,
            )
        )
        return await self._propagation.propagate(tenant_id, correction.id)
