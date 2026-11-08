"""Serviço público do Evidence Ledger (ADR-0003).

O serviço gera ``id`` e ``content_hash``; ``created_at`` vem do banco. A transação
pertence ao chamador (``tenant_session``): o serviço não faz commit, para que a
correção e a propagação de ``needs_review`` (#11) possam ocorrer na mesma transação.
"""

from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from basho.evidence.contracts import EventKind, EvidenceEvent, NewEvidenceEvent
from basho.evidence.domain.hashing import HASH_VERSION, compute_content_hash
from basho.evidence.domain.rules import (
    EvidenceNotFoundError,
    EvidenceValidationError,
    validate_event_shape,
    validate_supersedes_target,
)
from basho.evidence.models import EvidenceEventRow
from basho.evidence.repository import EvidenceRepository

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


def _to_event(row: EvidenceEventRow) -> EvidenceEvent:
    return EvidenceEvent.model_validate(
        {
            "id": row.id,
            "tenant_id": row.tenant_id,
            "project_id": row.project_id,
            "kind": row.kind,
            "source": row.source,
            "source_ref": row.source_ref,
            "actor": row.actor,
            "payload": row.payload,
            "content_hash": row.content_hash,
            "supersedes": row.supersedes,
            "is_synthetic": row.is_synthetic,
            "created_at": row.created_at,
        }
    )


def _insert_values(event: NewEvidenceEvent) -> dict[str, Any]:
    """Colunas da linha: conteúdo do evento mais id, hash e versão do hash do serviço."""
    return {
        "id": uuid4(),
        "tenant_id": event.tenant_id,
        "project_id": event.project_id,
        "kind": event.kind.value,
        "source": event.source.value,
        "source_ref": event.source_ref,
        "actor": event.actor.model_dump(mode="json"),
        "payload": event.payload,
        "supersedes": event.supersedes,
        "is_synthetic": event.is_synthetic,
        "content_hash": compute_content_hash(event),
        "hash_version": HASH_VERSION,
    }


class EvidenceService:
    def __init__(self, session: AsyncSession) -> None:
        self._repository = EvidenceRepository(session)

    async def _require_session_tenant(self, tenant_id: UUID) -> None:
        """A sessão deve ter sido aberta para o mesmo tenant (``tenant_session``)."""
        if await self._repository.current_tenant_setting() != str(tenant_id):
            raise EvidenceValidationError("tenant da sessão ausente ou diferente do informado")

    async def append(self, event: NewEvidenceEvent) -> EvidenceEvent:
        """Valida, calcula id/hash e grava um novo evento."""
        await self._require_session_tenant(event.tenant_id)
        validate_event_shape(event)
        if event.supersedes is not None:
            target_project = await self._repository.project_of(event.tenant_id, event.supersedes)
            validate_supersedes_target(event, target_project)
        try:
            row = await self._repository.insert(_insert_values(event))
        except IntegrityError:
            raise EvidenceValidationError("evento viola uma restrição de integridade") from None
        return _to_event(row)

    async def get(self, tenant_id: UUID, event_id: UUID) -> EvidenceEvent:
        await self._require_session_tenant(tenant_id)
        row = await self._repository.get(tenant_id, event_id)
        if row is None:
            raise EvidenceNotFoundError("evento não encontrado neste tenant")
        return _to_event(row)

    async def missing_ids(
        self, tenant_id: UUID, project_id: UUID, ids: Iterable[UUID]
    ) -> set[UUID]:
        """IDs que NÃO existem no ledger do tenant e do projeto (uma única consulta)."""
        await self._require_session_tenant(tenant_id)
        wanted = set(ids)
        if not wanted:
            return set()
        found = await self._repository.existing_ids(tenant_id, project_id, sorted(wanted, key=str))
        return wanted - found

    async def get_many(
        self, tenant_id: UUID, project_id: UUID, ids: Iterable[UUID]
    ) -> list[EvidenceEvent]:
        """Eventos existentes entre ``ids``, só do tenant e do projeto (uma consulta)."""
        await self._require_session_tenant(tenant_id)
        wanted = sorted(set(ids), key=str)
        if not wanted:
            return []
        rows = await self._repository.get_many(tenant_id, project_id, wanted)
        return [_to_event(row) for row in rows]

    async def query(
        self,
        tenant_id: UUID,
        *,
        project_id: UUID | None = None,
        kinds: Sequence[EventKind] | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
        before: tuple[datetime, UUID] | None = None,
    ) -> list[EvidenceEvent]:
        """Lista eventos do tenant, do mais novo ao mais antigo.

        ``before`` é o cursor ``(created_at, id)`` do último item da página anterior.
        ``limit`` é limitado a ``MAX_PAGE_SIZE``.
        """
        await self._require_session_tenant(tenant_id)
        if kinds is not None and len(kinds) == 0:
            return []
        bounded = max(1, min(limit, MAX_PAGE_SIZE))
        rows = await self._repository.query(
            tenant_id,
            project_id=project_id,
            kinds=[kind.value for kind in kinds] if kinds else None,
            limit=bounded,
            before=before,
        )
        return [_to_event(row) for row in rows]
