"""Seed sintético da demonstração (#14): um projeto de P&D com evidências, artefatos e vereditos.

Tudo é marcado ``is_synthetic`` (CLAUDE.md, regra 9) e nada aqui é dado formal: nenhuma hora,
valor, participante ou elegibilidade é gravado como fato. Os artefatos são o que o Maker e o
Checker gravariam, para a demonstração poder mostrar pendências, aprovação e dossiê sem
depender de LLM nem de rede.

Uso (como o login da API, nunca o dono do banco)::

    uv run python -m basho.seed

É idempotente: se o projeto da demo já existe, só imprime os identificadores.
"""

import asyncio
import json
import selectors
import sys
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from basho.config import get_settings
from basho.db import create_engine, create_session_factory, tenant_session
from basho.evidence import EvidenceService
from basho.evidence.contracts import (
    Actor,
    ActorType,
    EventKind,
    EventSource,
    NewEvidenceEvent,
)
from basho.projects import ProjectService

DEMO_PROJECT_NAME = "Demo — Quantização de modelos de detecção de falhas"
ELIGIBILITY_NOTE = "Potencialmente qualificável, sujeito a análise dos responsáveis."
SYSTEM = Actor(type=ActorType.SYSTEM, id="seed-demo")
MAKER = Actor(type=ActorType.AGENT, id="maker", model="seed-demo-maker")
CHECKER = Actor(type=ActorType.AGENT, id="checker", model="seed-demo-checker")
PASS = {"verdict": "pass", "issues": [], "unsupported_claims": [], "checker": "deterministic"}

# Commits sintéticos (espelham tests/fixtures/github/commits.json).
COMMITS: tuple[tuple[str, str, str, str], ...] = (
    (
        "a1f3c9e",
        "ana-pesquisadora",
        "2026-10-20T13:00:00Z",
        "exp(quant): baseline fp16 + script de benchmark",
    ),
    (
        "b7d2e10",
        "ana-pesquisadora",
        "2026-10-21T16:22:00Z",
        "exp(quant): int8 estático e dinâmico; registrar métricas",
    ),
    (
        "c94ab33",
        "ana-pesquisadora",
        "2026-10-22T11:05:00Z",
        "exp(quant): comparar precisão por classe no dataset de vibração",
    ),
    ("d0e1f22", "bruno-eng", "2026-10-28T09:10:00Z", "exp(data): SMOTE no dataset de vibração"),
)


def _commit_event(
    tenant_id: UUID, project_id: UUID, sha: str, author: str, date: str, message: str
) -> NewEvidenceEvent:
    return NewEvidenceEvent(
        tenant_id=tenant_id,
        project_id=project_id,
        kind=EventKind.COMMIT_OBSERVED,
        source=EventSource.GITHUB,
        source_ref=sha,
        actor=SYSTEM,
        payload={"sha": sha, "author": author, "date": date, "message": message},
        is_synthetic=True,
    )


def _draft(
    project_id: UUID,
    activity_id: UUID,
    title: str,
    summary: str,
    claims: list[dict[str, Any]],
    missing: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "project_id": str(project_id),
        "activity_id": str(activity_id),
        "title": title,
        "summary": summary,
        "claims": claims,
        "formal_hours_event_ids": [],
        "participant_ids": [],
        "missing": missing,
        "eligibility_note": ELIGIBILITY_NOTE,
    }


async def _artifact(
    ledger: EvidenceService,
    tenant_id: UUID,
    project_id: UUID,
    draft: dict[str, Any],
    *,
    status: str,
    unsupported: list[dict[str, str]],
) -> UUID:
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
                "draft": draft,
            },
            is_synthetic=True,
        )
    )
    checker_result = (
        PASS
        if status == "verified"
        else {
            "verdict": "fail",
            "issues": [],
            "unsupported_claims": unsupported,
            "checker": "seed-demo-checker",
        }
    )
    await ledger.append(
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
                "deterministic": PASS,
                "checker": checker_result,
            },
            is_synthetic=True,
        )
    )
    return artifact.id


async def _existing(session: AsyncSession, tenant_id: UUID) -> UUID | None:
    row = await session.execute(
        text("SELECT id FROM projects WHERE tenant_id = :t AND name = :n LIMIT 1"),
        {"t": tenant_id, "n": DEMO_PROJECT_NAME},
    )
    found = row.scalar_one_or_none()
    return UUID(str(found)) if found is not None else None


async def seed_demo(session: AsyncSession, tenant_id: UUID) -> dict[str, str]:
    """Cria o projeto da demonstração dentro da transação do tenant."""
    existing = await _existing(session, tenant_id)
    if existing is not None:
        return {"project_id": str(existing), "created": "false"}

    projects = ProjectService(session)
    ledger = EvidenceService(session)
    project_id = await projects.create_project(
        tenant_id,
        DEMO_PROJECT_NAME,
        description="Projeto sintético de P&D: reduzir latência de inferência embarcada.",
        is_synthetic=True,
    )
    quant = await projects.create_activity(
        tenant_id, project_id, "Quantização do modelo de detecção", is_synthetic=True
    )
    rebalance = await projects.create_activity(
        tenant_id, project_id, "Rebalanceamento do dataset de vibração", is_synthetic=True
    )
    ids = {
        sha: (await ledger.append(_commit_event(tenant_id, project_id, sha, *rest))).id
        for sha, *rest in COMMITS
    }
    verified = await _artifact(
        ledger,
        tenant_id,
        project_id,
        _draft(
            project_id,
            quant,
            "Quantização do modelo de detecção de falhas",
            "Experimentos de quantização para reduzir latência de inferência embarcada.",
            [
                {
                    "section": "technological_challenge",
                    "evidence_ids": [str(ids["a1f3c9e"])],
                    "text": (
                        "Reduzir latência de inferência sem perda relevante de precisão "
                        "em hardware embarcado."
                    ),
                },
                {
                    "section": "result",
                    "evidence_ids": [str(ids["b7d2e10"]), str(ids["c94ab33"])],
                    "text": (
                        "Foram comparadas as variantes int8 estática e dinâmica; "
                        "as métricas por classe foram registradas."
                    ),
                },
                {
                    "section": "uncertainty",
                    "evidence_ids": [str(ids["c94ab33"])],
                    "text": (
                        "Ainda não se sabe se a perda de precisão em algumas classes vem "
                        "da calibração ou do desbalanceamento."
                    ),
                },
            ],
            [],
        ),
        status="verified",
        unsupported=[],
    )
    needs_human = await _artifact(
        ledger,
        tenant_id,
        project_id,
        _draft(
            project_id,
            rebalance,
            "Rebalanceamento do dataset de vibração com SMOTE",
            "Tentativa de mitigar o desbalanceamento de classes antes de re-treinar.",
            [
                {
                    "section": "technological_challenge",
                    "evidence_ids": [str(ids["d0e1f22"])],
                    "text": "Mitigar o desbalanceamento de classes do dataset de vibração.",
                },
                {
                    "section": "result",
                    "evidence_ids": [str(ids["d0e1f22"])],
                    "text": "O SMOTE melhorou a precisão nas classes minoritárias.",
                },
            ],
            [
                {
                    "field": "technical_justification",
                    "ask_role": "pesquisador",
                    "question": "Qual hipótese motivou o SMOTE e qual critério define sucesso?",
                },
                {
                    "field": "formal_hours",
                    "ask_role": "coordenador",
                    "question": (
                        "Quantas horas cada participante dedicou a esta atividade, "
                        "segundo o registro oficial?"
                    ),
                },
            ],
        ),
        status="needs_human",
        unsupported=[
            {
                "claim_text": "O SMOTE melhorou a precisão nas classes minoritárias.",
                "reason": "O commit só registra a aplicação do SMOTE, sem métrica de resultado.",
            }
        ],
    )
    return {
        "project_id": str(project_id),
        "verified_artifact_id": str(verified),
        "needs_human_artifact_id": str(needs_human),
        "created": "true",
    }


async def main() -> None:
    settings = get_settings()
    engine = create_engine(settings.database_url.get_secret_value())
    try:
        factory = create_session_factory(engine)
        async with tenant_session(factory, settings.tenant_id) as session:
            result = await seed_demo(session, settings.tenant_id)
    finally:
        await engine.dispose()
    sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")


def run() -> None:
    asyncio.run(main(), loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()))


if __name__ == "__main__":
    run()
