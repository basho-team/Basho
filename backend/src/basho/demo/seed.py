"""Seed sintético e idempotente da demo: `uv run python -m basho.demo.seed`.

Grava no ledger, como **dados sintéticos** (`is_synthetic=True`):
- eventos de GitHub fictícios (PRs/commits) das pesquisadoras Ana e Bia;
- um registro formal de horas de Bia (origem `formal_system`, RH fictício); Ana fica sem
  registro formal, para a demo mostrar a lacuna;
- o relatório v1 de Bia, gravado pelo ator `system:demo-seed` (não simula autoria humana;
  a revisão de Bia é feita na interface);
- o rascunho automático de Ana (regras, sem LLM; ator `system:auto-draft:regras-v1`).
Reexecutar não duplica nada (marca `demo:` em `source_ref`).
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from basho.agent.artifacts import (
    ClaimSection,
    ClaimStatus,
    ExperimentOutcome,
    ExperimentOutcomeKind,
    MissingInformation,
    ReportClaim,
    ResearchReportDraft,
)
from basho.config import get_settings
from basho.db import create_engine, create_session_factory, tenant_session
from basho.demo.context import ANA, BIA, PERIOD, PROJECT_ID
from basho.evidence import EvidenceService
from basho.evidence.contracts import Actor, ActorType, EventKind, EventSource, NewEvidenceEvent
from basho.logging import configure_logging, get_logger
from basho.reports.service import ReportAlreadyExistsError, ReportQueryService, ReportService

SEED = Actor(type=ActorType.SYSTEM, id="demo-seed")
GITHUB = Actor(type=ActorType.SYSTEM, id="demo-seed:github-fictício")

# (chave, pesquisadora, kind, origem, payload)
EVENTS: tuple[tuple[str, UUID, EventKind, EventSource, dict[str, Any]], ...] = (
    (
        "demo:pr-42",
        ANA.id,
        EventKind.PULL_REQUEST_OBSERVED,
        EventSource.GITHUB,
        {
            "title": "PR #42 — quantização int8 dinâmica",
            "description": "Aplica quantização int8 dinâmica; benchmark: latência 38% menor.",
            "author": "ana-ficticia",
        },
    ),
    (
        "demo:commit-c94ab",
        ANA.id,
        EventKind.COMMIT_OBSERVED,
        EventSource.GITHUB,
        {
            "title": "c94ab — benchmark de precisão pós-quantização",
            "description": "Precisão caiu 4,1 p.p. no dataset de vibração após int8.",
            "author": "ana-ficticia",
        },
    ),
    (
        "demo:pr-43",
        ANA.id,
        EventKind.PULL_REQUEST_OBSERVED,
        EventSource.GITHUB,
        {
            "title": "PR #43 — rebalanceamento com SMOTE",
            "description": "Rebalanceia o dataset de vibração com SMOTE. Sem hipótese descrita.",
            "author": "ana-ficticia",
        },
    ),
    (
        "demo:commit-b101",
        BIA.id,
        EventKind.COMMIT_OBSERVED,
        EventSource.GITHUB,
        {
            "title": "b101 — calibração por percentil 99,9",
            "description": "Calibração por percentil aplicada a 500 amostras de validação.",
            "author": "bia-ficticia",
        },
    ),
    (
        "demo:bench-a",
        BIA.id,
        EventKind.COMMIT_OBSERVED,
        EventSource.GITHUB,
        {
            "title": "Bancada A — latência 41 ms",
            "description": "Medição na bancada A: 41 ms com o modelo calibrado.",
            "author": "bia-ficticia",
        },
    ),
    (
        "demo:bench-b",
        BIA.id,
        EventKind.COMMIT_OBSERVED,
        EventSource.GITHUB,
        {
            "title": "Bancada B — latência 63 ms",
            "description": "Medição na bancada B: 63 ms com o mesmo modelo calibrado.",
            "author": "bia-ficticia",
        },
    ),
    (
        "demo:rh-horas-bia",
        BIA.id,
        EventKind.FORMAL_HOURS_DECLARED,
        EventSource.FORMAL_SYSTEM,
        {
            "title": "Registro formal de horas — outubro/2026 (RH fictício)",
            "description": "Horas declaradas e confirmadas no sistema de RH fictício.",
            "hours": 96,
            "declared_by_role": "rh",
        },
    ),
)


async def _ensure_events(ledger: EvidenceService, tenant_id: UUID) -> dict[str, UUID]:
    existing = await ledger.query(tenant_id, project_id=PROJECT_ID, limit=200)
    ids = {
        e.source_ref: e.id for e in existing if e.source_ref and e.source_ref.startswith("demo:")
    }
    for key, researcher, kind, source, payload in EVENTS:
        if key in ids:
            continue
        event = await ledger.append(
            NewEvidenceEvent(
                tenant_id=tenant_id,
                project_id=PROJECT_ID,
                kind=kind,
                source=source,
                source_ref=key,
                actor=GITHUB if source is EventSource.GITHUB else SEED,
                payload={**payload, "researcher_id": str(researcher)},
                is_synthetic=True,
            )
        )
        ids[key] = event.id
    return ids


def _bia_draft(ids: dict[str, UUID]) -> ResearchReportDraft:
    method, a, b = ids["demo:commit-b101"], ids["demo:bench-a"], ids["demo:bench-b"]
    return ResearchReportDraft(
        project_id=PROJECT_ID,
        researcher_id=BIA.id,
        period=PERIOD,
        summary="Calibração por percentil para a quantização e comparação entre bancadas.",
        claims=(
            ReportClaim(
                section=ClaimSection.METHOD,
                text="Calibração por percentil 99,9 aplicada a 500 amostras de validação.",
                status=ClaimStatus.SUPPORTED,
                evidence_ids=(method,),
            ),
            ReportClaim(
                section=ClaimSection.RESULT,
                text="As duas bancadas reportam latências incompatíveis para o mesmo modelo.",
                status=ClaimStatus.DISPUTED,
                evidence_ids=(a, b),
                dispute_reason="Bancada A mede 41 ms e B mede 63 ms sem diferença documentada.",
            ),
        ),
        experiments=(
            ExperimentOutcome(
                description="Calibração por percentil para recuperar precisão após int8.",
                outcome=ExperimentOutcomeKind.INCONCLUSIVE,
                evidence_ids=(method,),
            ),
        ),
        missing=(
            MissingInformation(
                field="bench_config",
                question="Qual configuração de hardware difere entre as bancadas A e B?",
                ask_role="pesquisador",
            ),
        ),
        formal_hours_event_ids=(ids["demo:rh-horas-bia"],),
    )


async def seed() -> dict[str, Any]:
    settings = get_settings()
    engine = create_engine(settings.database_url.get_secret_value())
    factory = create_session_factory(engine)
    try:
        async with tenant_session(factory, settings.tenant_id) as session:
            ids = await _ensure_events(EvidenceService(session), settings.tenant_id)
            try:
                report = await ReportService(session).create_report(
                    settings.tenant_id,
                    _bia_draft(ids),
                    actor=SEED,
                    source=EventSource.SYSTEM,
                    is_synthetic=True,
                )
                report_id = report.version.id
            except ReportAlreadyExistsError as exists:
                report_id = exists.current_version_id
            # Ana: rascunho automático (regras, sem LLM) pronto para leitura e confirmação.
            ana = await ReportQueryService(session).auto_draft(
                settings.tenant_id, PROJECT_ID, ANA.id, PERIOD
            )
    finally:
        await engine.dispose()
    return {
        "events": len(ids),
        "bia_report_version_id": str(report_id),
        "ana_report_version_id": str(ana.version.id),
    }


def main() -> None:
    configure_logging()
    result = asyncio.run(seed())
    get_logger(__name__).info("demo_seed_done", **result)


if __name__ == "__main__":
    main()
