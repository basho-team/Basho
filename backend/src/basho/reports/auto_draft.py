"""Rascunho automático do relatório a partir do ledger (regras determinísticas, sem LLM).

Usado enquanto o Maker (#8) não é acionado nesta demo (sem chave de API). Não interpreta nem
inventa: cada afirmação reproduz a descrição da própria fonte e a cita; o que as fontes não
dizem (hipótese, desfecho dos experimentos, horas) vira pergunta objetiva em `missing[]` ou
afirmação `pending`. Horas só por referência a `formal_hours_declared` do pesquisador.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from basho.agent.artifacts import (
    ClaimSection,
    ClaimStatus,
    MissingInformation,
    ReportClaim,
    ReportingPeriod,
    ResearchReportDraft,
)
from basho.evidence.contracts import Actor, ActorType, EventKind, EvidenceEvent

AUTO_DRAFT_ACTOR = Actor(type=ActorType.SYSTEM, id="auto-draft:regras-v1")
MIN_TEXT = 10
CLAIM_KINDS = {
    EventKind.ACTIVITY_RECORD: ClaimSection.METHOD,
    EventKind.COMMIT_OBSERVED: ClaimSection.METHOD,
    EventKind.PULL_REQUEST_OBSERVED: ClaimSection.METHOD,
    EventKind.TECHNICAL_JUSTIFICATION: ClaimSection.TECHNOLOGICAL_CHALLENGE,
}


class NothingToDraftError(LookupError):
    """Sem evidência do pesquisador no período: não há o que redigir."""


def belongs_to(event: EvidenceEvent, researcher_id: UUID) -> bool:
    owner = event.payload.get("researcher_id")
    return owner == str(researcher_id) or event.actor.id == str(researcher_id)


def _text(event: EvidenceEvent) -> str | None:
    title = str(event.payload.get("title") or "").strip()
    description = str(event.payload.get("description") or "").strip()
    text = f"{title}: {description}" if title and description else title or description
    return text if len(text) >= MIN_TEXT else None


def build_auto_draft(
    project_id: UUID,
    researcher_id: UUID,
    period: ReportingPeriod,
    events: Sequence[EvidenceEvent],
) -> ResearchReportDraft:
    own = [e for e in events if belongs_to(e, researcher_id) and "artifact" not in e.payload]
    own.sort(key=lambda e: (e.created_at, str(e.id)))
    claims: list[ReportClaim] = []
    for event in own:
        section = CLAIM_KINDS.get(event.kind)
        text = _text(event)
        if section is None or text is None:
            continue
        claims.append(
            ReportClaim(
                section=section, text=text, status=ClaimStatus.SUPPORTED, evidence_ids=(event.id,)
            )
        )
    if not claims:
        raise NothingToDraftError("nenhuma evidência do pesquisador para redigir")
    claims.append(
        ReportClaim(
            section=ClaimSection.HYPOTHESIS,
            text="Hipótese de trabalho do período não está registrada nas fontes.",
            status=ClaimStatus.PENDING,
            question="Qual hipótese orientou o trabalho do período e qual critério define sucesso?",
            ask_role="pesquisador",
        )
    )
    hours = tuple(e.id for e in own if e.kind is EventKind.FORMAL_HOURS_DECLARED)
    missing = [
        MissingInformation(
            field="experiment_outcomes",
            question="Quais experimentos do período deram resultado positivo, negativo ou "
            "inconclusivo, e qual fonte mostra cada desfecho?",
            ask_role="pesquisador",
        )
    ]
    if not hours:
        missing.append(
            MissingInformation(
                field="formal_hours",
                question="Quais horas o registro formal da coordenação informa para o período?",
                ask_role="coordenador",
            )
        )
    return ResearchReportDraft(
        project_id=project_id,
        researcher_id=researcher_id,
        period=period,
        summary=(
            f"Rascunho automático com {len(claims) - 1} evidência(s) do período, gerado por "
            "regras a partir do ledger. Revise e confirme ou corrija."
        ),
        claims=tuple(claims),
        missing=tuple(missing),
        formal_hours_event_ids=hours,
    )
