"""Consultas da propagação de correções (#11): só SELECT e advisory lock (ADR-0003).

Tudo roda sob a RLS do tenant da sessão; os filtros por ``tenant_id``/``project_id`` são
defesa em profundidade e usam os índices ``(tenant_id, project_id, created_at, id)``.
"""

import json
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from basho.evidence.contracts import ArtifactStatus, EventKind

ARTIFACT_KIND = EventKind.ACTIVITY_RECORD.value
STATUS_KIND = EventKind.STATUS_CHANGED.value

# Citação = id em qualquer `evidence_ids` ou `formal_hours_event_ids` do rascunho
# (claims, experimentos, lacunas resolvidas), no formato gravado pelo Maker (#8) e por
# versões de relatório (#39).
_CITING_ARTIFACTS_SQL = text(
    """
    SELECT e.id
    FROM evidence_events e
    WHERE e.tenant_id = :tenant_id
      AND e.project_id = :project_id
      AND e.kind = :artifact_kind
      AND (
        jsonb_path_exists(e.payload, '$.draft.**.evidence_ids[*] ? (@ == $id)',
                          CAST(:vars AS jsonb))
        OR jsonb_path_exists(e.payload, '$.draft.**.formal_hours_event_ids[*] ? (@ == $id)',
                             CAST(:vars AS jsonb))
      )
      AND NOT EXISTS (
        SELECT 1 FROM evidence_events s
        WHERE s.tenant_id = e.tenant_id AND s.supersedes = e.id
      )
    ORDER BY e.created_at, e.id
    """
)

_HAS_MARK_SQL = text(
    """
    SELECT EXISTS (
        SELECT 1 FROM evidence_events
        WHERE tenant_id = :tenant_id AND project_id = :project_id AND kind = :status_kind
          AND payload @> CAST(:mark AS jsonb)
    )
    """
)

# Último status_changed por artefato; fica pendente se o último é needs_review e o
# artefato não foi substituído por uma versão nova.
_PENDING_SQL = text(
    """
    SELECT latest.id, latest.payload, latest.created_at
    FROM (
        SELECT DISTINCT ON (s.payload ->> 'artifact_event_id') s.id, s.payload, s.created_at
        FROM evidence_events s
        WHERE s.tenant_id = :tenant_id AND s.project_id = :project_id
          AND s.kind = :status_kind
        ORDER BY s.payload ->> 'artifact_event_id', s.created_at DESC, s.id DESC
    ) AS latest
    WHERE latest.payload ->> 'status' = :needs_review
      AND NOT EXISTS (
        SELECT 1 FROM evidence_events n
        WHERE n.tenant_id = :tenant_id
          AND n.supersedes = CAST(latest.payload ->> 'artifact_event_id' AS uuid)
      )
    ORDER BY latest.created_at, latest.id
    """
)

_LATEST_STATUS_SQL = text(
    """
    SELECT id, payload FROM evidence_events
    WHERE tenant_id = :tenant_id AND kind = :status_kind
      AND payload @> CAST(:artifact AS jsonb)
    ORDER BY created_at DESC, id DESC
    LIMIT 1
    """
)


class PropagationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock(self, key: str) -> None:
        """Serializa propagações da mesma correção até o fim da transação."""
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": key}
        )

    async def citing_artifacts(
        self, tenant_id: UUID, project_id: UUID, cited_id: UUID
    ) -> list[UUID]:
        params = {
            "tenant_id": tenant_id,
            "project_id": project_id,
            "artifact_kind": ARTIFACT_KIND,
            "vars": json.dumps({"id": str(cited_id)}),
        }
        return list((await self._session.execute(_CITING_ARTIFACTS_SQL, params)).scalars())

    async def has_mark(self, tenant_id: UUID, project_id: UUID, mark: dict[str, str]) -> bool:
        params = {
            "tenant_id": tenant_id,
            "project_id": project_id,
            "status_kind": STATUS_KIND,
            "mark": json.dumps(mark),
        }
        return bool((await self._session.execute(_HAS_MARK_SQL, params)).scalar_one())

    async def pending(
        self, tenant_id: UUID, project_id: UUID
    ) -> list[tuple[UUID, dict[str, object], datetime]]:
        params = {
            "tenant_id": tenant_id,
            "project_id": project_id,
            "status_kind": STATUS_KIND,
            "needs_review": ArtifactStatus.NEEDS_REVIEW.value,
        }
        rows = (await self._session.execute(_PENDING_SQL, params)).all()
        return [(row.id, row.payload, row.created_at) for row in rows]

    async def latest_status(
        self, tenant_id: UUID, artifact_event_id: UUID
    ) -> tuple[UUID, dict[str, object]] | None:
        params = {
            "tenant_id": tenant_id,
            "status_kind": STATUS_KIND,
            "artifact": json.dumps({"artifact_event_id": str(artifact_event_id)}),
        }
        row = (await self._session.execute(_LATEST_STATUS_SQL, params)).one_or_none()
        return None if row is None else (row.id, row.payload)
