"""Artefato produzido pelo Maker: rascunho de registro de atividade de P&D (ADR-0004).

Toda afirmação cita evidências. Horas e participantes só por referência a eventos formais.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Self
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MIN_CITATIONS_PER_CLAIM = 1
MIN_QUESTION_LENGTH = 10
DEFAULT_ELIGIBILITY_NOTE = "Potencialmente qualificável, sujeito a análise dos responsáveis."


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
        default=DEFAULT_ELIGIBILITY_NOTE,
        description="Nunca afirmar enquadramento definitivo (ADR-0005)",
    )


# --- Relatório individual do pesquisador (perfil `research_report`, ADR-0009 proposta) ---


class ClaimStatus(StrEnum):
    """Status de uma afirmação de relatório (ADR-0009).

    `supported` aqui é só pré-condição de schema (≥ 1 evidência citada); a correspondência
    real entre texto e evidência é verificada pelos checks determinísticos (#9) e pelo Checker.
    """

    SUPPORTED = "supported"
    PENDING = "pending"
    DISPUTED = "disputed"


class Periodicity(StrEnum):
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"
    CUSTOM = "custom"


class ReportingPeriod(BaseModel):
    """Período coberto por um relatório de pesquisa (datas inclusivas, no fuso `timezone`).

    É um período operacional de acompanhamento e **não** se confunde com o ano-base fiscal
    da Lei do Bem: um relatório mensal não implica nenhum enquadramento nem apuração.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    start: date
    end: date
    timezone: str = Field(description="Nome IANA, ex.: America/Sao_Paulo")
    periodicity: Periodicity

    @field_validator("timezone")
    @classmethod
    def _timezone_is_iana(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        # OSError: nomes que são diretórios da base IANA ("America", "Etc") levantam
        # PermissionError/IsADirectoryError conforme o SO; devem virar erro de validação.
        except (ZoneInfoNotFoundError, ValueError, OSError) as exc:
            msg = f"timezone IANA desconhecido: {value!r}"
            raise ValueError(msg) from exc
        return value

    @model_validator(mode="after")
    def _end_not_before_start(self) -> Self:
        if self.end < self.start:
            msg = "period.end não pode ser anterior a period.start"
            raise ValueError(msg)
        return self


class ReportClaim(BaseModel):
    """Afirmação de relatório com status explícito (distinta de `Claim`, que é sempre citada).

    Regras de schema (campos de outro status são proibidos):
    - `supported` ⇒ ≥ 1 `evidence_id`; sem `question`, `ask_role` nem `dispute_reason`;
    - `pending` ⇒ `question` objetiva e `ask_role` (vira pendência); sem `dispute_reason`;
    - `disputed` ⇒ `dispute_reason` e ≥ 1 evidência em conflito; sem `question`/`ask_role`.

    `supported` não garante que a evidência sustente o texto: isso é papel do Checker.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    section: ClaimSection
    text: str = Field(min_length=10)
    status: ClaimStatus
    evidence_ids: tuple[UUID, ...] = ()
    question: str | None = Field(default=None, min_length=MIN_QUESTION_LENGTH)
    ask_role: str | None = Field(default=None, min_length=1)
    dispute_reason: str | None = Field(default=None, min_length=MIN_QUESTION_LENGTH)

    @field_validator("evidence_ids")
    @classmethod
    def _evidence_ids_unique(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        if len(set(value)) != len(value):
            msg = "evidence_ids não pode ter IDs repetidos"
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def _status_preconditions(self) -> Self:
        has_question = self.question is not None or self.ask_role is not None
        if self.status is ClaimStatus.SUPPORTED:
            if len(self.evidence_ids) < MIN_CITATIONS_PER_CLAIM:
                msg = "claim supported exige ao menos uma evidência citada"
                raise ValueError(msg)
            if self.dispute_reason is not None or has_question:
                msg = "claim supported não pode ter dispute_reason, question nem ask_role"
                raise ValueError(msg)
        elif self.status is ClaimStatus.PENDING:
            if self.question is None or self.ask_role is None:
                msg = "claim pending exige question objetiva e ask_role"
                raise ValueError(msg)
            if self.dispute_reason is not None:
                msg = "claim pending não pode ter dispute_reason; use status disputed"
                raise ValueError(msg)
        else:
            if self.dispute_reason is None or not self.evidence_ids:
                msg = "claim disputed exige dispute_reason e as evidências em conflito"
                raise ValueError(msg)
            if has_question:
                msg = "claim disputed não pode ter question nem ask_role; use missing[]"
                raise ValueError(msg)
        return self


class ExperimentOutcomeKind(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    INCONCLUSIVE = "inconclusive"


class ExperimentOutcome(BaseModel):
    """Desfecho de um experimento no período. Negativo e inconclusivo são resultados válidos."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    description: str = Field(min_length=10)
    outcome: ExperimentOutcomeKind
    evidence_ids: tuple[UUID, ...] = Field(min_length=MIN_CITATIONS_PER_CLAIM)


class ResearchReportDraft(BaseModel):
    """Saída estruturada do perfil `research_report`: relatório individual por período.

    Sem campos numéricos de horas ou valores: horas só por referência a eventos formais.

    Pré-condição de schema para resultados: toda evidência citada por um claim `supported`
    da seção `result` precisa estar coberta por algum `ExperimentOutcome`, que declara o
    desfecho explícito (`positive | negative | inconclusive`). Isso **não** garante sozinho que
    nenhum resultado negativo foi omitido: a garantia vem do check determinístico (#9), que
    compara `experiments[]` com os experimentos do período no ledger.

    `eligibility_note` é fixa (CLAUDE.md, regra 7): o Maker não redige enquadramento.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    project_id: UUID
    researcher_id: UUID = Field(description="Referência a membro do projeto; nunca inferido")
    period: ReportingPeriod
    summary: str = Field(min_length=20)
    claims: tuple[ReportClaim, ...] = Field(min_length=1)
    experiments: tuple[ExperimentOutcome, ...] = ()
    missing: tuple[MissingInformation, ...] = ()
    formal_hours_event_ids: tuple[UUID, ...] = Field(
        default=(), description="Só referências a eventos FORMAL_HOURS_DECLARED"
    )
    eligibility_note: str = Field(
        default=DEFAULT_ELIGIBILITY_NOTE,
        description="Nunca afirmar enquadramento definitivo (ADR-0005)",
    )

    @field_validator("eligibility_note")
    @classmethod
    def _eligibility_note_is_fixed(cls, value: str) -> str:
        if value != DEFAULT_ELIGIBILITY_NOTE:
            msg = f"eligibility_note deve ser exatamente {DEFAULT_ELIGIBILITY_NOTE!r}"
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def _results_have_explicit_outcomes(self) -> Self:
        covered = {eid for experiment in self.experiments for eid in experiment.evidence_ids}
        for claim in self.claims:
            if claim.section is not ClaimSection.RESULT:
                continue
            if claim.status is not ClaimStatus.SUPPORTED:
                continue
            if not covered.issuperset(claim.evidence_ids):
                msg = (
                    "claim supported de resultado com evidência sem ExperimentOutcome: "
                    "declare o desfecho (positive, negative ou inconclusive)"
                )
                raise ValueError(msg)
        return self
