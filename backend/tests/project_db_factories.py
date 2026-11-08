"""Fábricas para os testes de projetos/pendências (dados sintéticos, sem LLM).

Grava no ledger o que o Maker e o Checker gravariam: o artefato `activity_record` (source agent)
e o `verification_result` com o status pedido, citando evidências reais do projeto.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from basho.evidence import EvidenceService
from basho.evidence.contracts import (
    Actor,
    ActorType,
    EventKind,
    EventSource,
    EvidenceEvent,
    NewEvidenceEvent,
)
from basho.projects import ProjectService
from evidence_factories import make_event

FIXTURE = Path(__file__).parent / "fixtures" / "activity_record_draft.json"
MAKER = Actor(type=ActorType.AGENT, id="maker", model="test-maker-model")
CHECKER = Actor(type=ActorType.AGENT, id="checker", model="test-checker-model")
PASS_RESULT = {
    "verdict": "pass",
    "issues": [],
    "unsupported_claims": [],
    "checker": "deterministic",
}
FAIL_RESULT = {
    "verdict": "fail",
    "issues": [],
    "unsupported_claims": [
        {"claim_text": "Int8 dinâmico reduziu a latência", "reason": "sem evidência"}
    ],
    "checker": "test-checker-model",
}


@dataclass(frozen=True)
class SeededArtifact:
    artifact: EvidenceEvent
    verification: EvidenceEvent | None
    cited: tuple[UUID, ...]


async def seed_project(session: AsyncSession, tenant_id: UUID) -> UUID:
    service = ProjectService(session)
    project_id = await service.create_project(
        tenant_id, "Projeto sintético de quantização", is_synthetic=True
    )
    await service.create_activity(
        tenant_id, project_id, "Quantização do modelo de detecção", is_synthetic=True
    )
    return project_id


def _draft(cited: dict[str, UUID], project_id: UUID, *, with_missing: bool) -> dict[str, Any]:
    text = FIXTURE.read_text(encoding="utf-8")
    for old_id, new_id in cited.items():
        text = text.replace(old_id, str(new_id))
    data: dict[str, Any] = json.loads(text)
    data.pop("_synthetic", None)
    data["project_id"] = str(project_id)
    if not with_missing:
        data["missing"] = []
    return data


async def seed_artifact(
    session: AsyncSession,
    tenant_id: UUID,
    project_id: UUID,
    *,
    status: str | None,
    with_missing: bool = True,
) -> SeededArtifact:
    """Artefato do Maker + veredito (`status` None = sem veredito ainda)."""
    ledger = EvidenceService(session)
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    old_ids = sorted({eid for claim in raw["claims"] for eid in claim["evidence_ids"]})
    cited = {
        old: (
            await ledger.append(
                make_event(tenant_id=tenant_id, project_id=project_id, source_ref=old)
            )
        ).id
        for old in old_ids
    }
    artifact = await ledger.append(
        NewEvidenceEvent(
            tenant_id=tenant_id,
            project_id=project_id,
            kind=EventKind.ACTIVITY_RECORD,
            source=EventSource.AGENT,
            source_ref=f"run:{uuid4()}",
            actor=MAKER,
            payload={
                "artifact_type": "ActivityRecordDraft",
                "task_kind": "research_report",
                "prompt_version": "v2",
                "run_id": str(uuid4()),
                "attempts": 1,
                "status": "proposed",
                "draft": _draft(cited, project_id, with_missing=with_missing),
            },
            is_synthetic=True,
        )
    )
    verification = None
    if status is not None:
        verification = await ledger.append(
            NewEvidenceEvent(
                tenant_id=tenant_id,
                project_id=project_id,
                kind=EventKind.VERIFICATION_RESULT,
                source=EventSource.AGENT,
                source_ref=f"artifact:{artifact.id}",
                actor=CHECKER,
                payload={
                    "artifact_event_id": str(artifact.id),
                    "status": status,
                    "prompt_version": "v1",
                    "deterministic": PASS_RESULT,
                    "checker": PASS_RESULT if status == "verified" else FAIL_RESULT,
                },
                is_synthetic=True,
            )
        )
    return SeededArtifact(artifact, verification, tuple(cited.values()))
