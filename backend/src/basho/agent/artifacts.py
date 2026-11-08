"""Artefato produzido pelo Maker: rascunho de registro de atividade de P&D (ADR-0004).

Toda afirmação cita evidências. Horas e participantes só por referência a eventos formais.
"""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

MIN_CITATIONS_PER_CLAIM = 1


class ClaimSection(StrEnum):
    TECHNOLOGICAL_CHALLENGE = "technological_challenge"
    HYPOTHESIS = "hypothesis"
    METHOD = "method"
    RESULT = "result"
    UNCERTAINTY = "uncertainty"


class Claim(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    section: ClaimSection
    text: str = Field(min_length=10)
    evidence_ids: tuple[UUID, ...] = Field(min_length=MIN_CITATIONS_PER_CLAIM)


class MissingInformation(BaseModel):
    """Lacuna que o Maker não pode preencher sozinho → vira pendência."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    field: str
    question: str = Field(min_length=10, description="Pergunta objetiva ao responsável")
    ask_role: str = Field(description="Ex.: pesquisador, coordenador, financeiro")


class ActivityRecordDraft(BaseModel):
    """Saída estruturada do Maker. Validada por schema antes dos checks determinísticos."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    project_id: UUID
    activity_id: UUID
    title: str = Field(min_length=5, max_length=200)
    summary: str = Field(min_length=20)
    claims: tuple[Claim, ...] = Field(min_length=1)
    formal_hours_event_ids: tuple[UUID, ...] = Field(
        default=(), description="Só referências a eventos FORMAL_HOURS_DECLARED"
    )
    participant_ids: tuple[UUID, ...] = Field(
        default=(), description="Só pessoas confirmadas em eventos formais"
    )
    missing: tuple[MissingInformation, ...] = ()
    eligibility_note: str = Field(
        default="Potencialmente qualificável, sujeito a análise dos responsáveis.",
        description="Nunca afirmar enquadramento definitivo (ADR-0005)",
    )
