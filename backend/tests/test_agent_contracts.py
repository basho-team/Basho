"""Testes de contrato do agente por perfis de tarefa (#38, ADR-0009 proposta). Sem LLM."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from basho.agent.artifacts import (
    ClaimSection,
    ClaimStatus,
    ExperimentOutcomeKind,
    ReportClaim,
    ReportingPeriod,
    ResearchReportDraft,
)
from basho.agent.runs import (
    ALLOWED_TRANSITIONS,
    AgentRun,
    InvalidRunTransitionError,
    RunError,
    RunStatus,
    can_transition,
    fail_or_retry,
    transition_run,
)
from basho.agent.tasks import (
    RESEARCH_REPORT_PROFILE,
    TOOL_REGISTRY_CONTEXT_KEY,
    ProfileNotAvailableError,
    TaskKind,
    TaskProfile,
    get_profile,
    load_prompt,
)
from basho.agent.tools import MVP_TOOLS, PermissionLevel

FIXTURES = Path(__file__).parent / "fixtures"
TERMINAL_STATUSES = (RunStatus.AWAITING_INPUT, RunStatus.COMPLETED, RunStatus.FAILED)


def load_report_fixture() -> dict[str, Any]:
    """Fixture sintética sem a marca `_synthetic` (o schema é `extra="forbid"`)."""
    raw: dict[str, Any] = json.loads(
        (FIXTURES / "research_report_draft.json").read_text(encoding="utf-8")
    )
    assert raw.pop("_synthetic") is True
    return raw


def run_kwargs(**overrides: Any) -> dict[str, Any]:
    now = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)
    base: dict[str, Any] = {
        "id": uuid4(),
        "tenant_id": uuid4(),
        "task_kind": TaskKind.RESEARCH_REPORT,
        "prompt_version": "v1",
        "status": RunStatus.QUEUED,
        "correlation_id": uuid4(),
        "idempotency_key": "research_report:2026-10:ana",
        "created_at": now,
        "updated_at": now,
    }
    return base | overrides


# --- ResearchReportDraft / ReportClaim ---


def test_research_report_fixture_matches_contract() -> None:
    # Arrange
    raw = load_report_fixture()

    # Act
    draft = ResearchReportDraft.model_validate(raw)

    # Assert
    statuses = {claim.status for claim in draft.claims}
    assert {ClaimStatus.SUPPORTED, ClaimStatus.PENDING} <= statuses
    assert ExperimentOutcomeKind.NEGATIVE in {exp.outcome for exp in draft.experiments}
    assert draft.formal_hours_event_ids == ()
    assert "formal_hours" in {item.field for item in draft.missing}


def test_research_report_rejects_unknown_fields() -> None:
    # Arrange
    raw = load_report_fixture() | {"total_hours": 160}

    # Act / Assert
    with pytest.raises(ValidationError):
        ResearchReportDraft.model_validate(raw)


def test_supported_claim_without_evidence_is_rejected() -> None:
    with pytest.raises(ValidationError, match="supported exige"):
        ReportClaim(
            section=ClaimSection.METHOD,
            text="Comparamos três variações de quantização.",
            status=ClaimStatus.SUPPORTED,
        )


def test_pending_claim_without_question_is_rejected() -> None:
    with pytest.raises(ValidationError, match="pending exige"):
        ReportClaim(
            section=ClaimSection.HYPOTHESIS,
            text="Hipótese do rebalanceamento ainda não registrada.",
            status=ClaimStatus.PENDING,
            ask_role="pesquisador",
        )


def test_pending_claim_without_evidence_is_accepted() -> None:
    # Act
    claim = ReportClaim(
        section=ClaimSection.HYPOTHESIS,
        text="Hipótese do rebalanceamento ainda não registrada.",
        status=ClaimStatus.PENDING,
        question="Qual hipótese motivou o rebalanceamento com SMOTE?",
        ask_role="pesquisador",
    )

    # Assert
    assert claim.evidence_ids == ()


def test_disputed_claim_without_reason_is_rejected() -> None:
    with pytest.raises(ValidationError, match="disputed exige"):
        ReportClaim(
            section=ClaimSection.RESULT,
            text="Latência caiu 38% segundo o PR, mas o benchmark diverge.",
            status=ClaimStatus.DISPUTED,
            evidence_ids=(uuid4(), uuid4()),
        )


def test_supported_result_without_experiment_outcome_is_rejected() -> None:
    # Arrange: remove o desfecho que cobre a evidência do claim de resultado.
    raw = load_report_fixture()
    raw["experiments"] = []

    # Act / Assert
    with pytest.raises(ValidationError, match="ExperimentOutcome"):
        ResearchReportDraft.model_validate(raw)


def test_supported_result_with_partially_covered_evidence_is_rejected() -> None:
    # Arrange: o claim de resultado cita uma evidência que nenhum desfecho cobre.
    raw = load_report_fixture()
    result_claim = next(c for c in raw["claims"] if c["section"] == "result")
    result_claim["evidence_ids"] = [*result_claim["evidence_ids"], str(uuid4())]

    # Act / Assert
    with pytest.raises(ValidationError, match="ExperimentOutcome"):
        ResearchReportDraft.model_validate(raw)


def test_eligibility_assertion_is_rejected() -> None:
    # Arrange
    raw = load_report_fixture() | {
        "eligibility_note": "O projeto é elegível e garante o incentivo."
    }

    # Act / Assert
    with pytest.raises(ValidationError, match="eligibility_note"):
        ResearchReportDraft.model_validate(raw)


@pytest.mark.parametrize(
    "extra",
    [
        {"question": "Pergunta que não cabe aqui?", "ask_role": "pesquisador"},
        {"dispute_reason": "Conflito que não cabe aqui."},
    ],
)
def test_supported_claim_with_fields_of_other_status_is_rejected(extra: dict[str, str]) -> None:
    with pytest.raises(ValidationError, match="supported não pode"):
        ReportClaim(
            section=ClaimSection.METHOD,
            text="Comparamos três variações de quantização.",
            status=ClaimStatus.SUPPORTED,
            evidence_ids=(uuid4(),),
            **extra,
        )


def test_claim_with_repeated_evidence_is_rejected() -> None:
    # Arrange
    evidence = uuid4()

    # Act / Assert
    with pytest.raises(ValidationError, match="repetidos"):
        ReportClaim(
            section=ClaimSection.METHOD,
            text="Comparamos três variações de quantização.",
            status=ClaimStatus.SUPPORTED,
            evidence_ids=(evidence, evidence),
        )


def test_whitespace_only_claim_text_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ReportClaim(
            section=ClaimSection.METHOD,
            text=" " * 20,
            status=ClaimStatus.SUPPORTED,
            evidence_ids=(uuid4(),),
        )


def test_pending_result_does_not_require_experiment_outcome() -> None:
    # Arrange
    raw = load_report_fixture()
    raw["experiments"] = []
    raw["claims"] = [
        {
            "section": "result",
            "text": "Resultado do rebalanceamento ainda não informado.",
            "status": "pending",
            "question": "Qual foi o resultado do rebalanceamento com SMOTE?",
            "ask_role": "pesquisador",
        }
    ]

    # Act
    draft = ResearchReportDraft.model_validate(raw)

    # Assert
    assert draft.claims[0].status is ClaimStatus.PENDING


# --- ReportingPeriod ---


def test_reporting_period_end_before_start_is_rejected() -> None:
    with pytest.raises(ValidationError, match="anterior"):
        ReportingPeriod.model_validate(
            {
                "start": "2026-10-31",
                "end": "2026-10-01",
                "timezone": "America/Sao_Paulo",
                "periodicity": "monthly",
            }
        )


@pytest.mark.parametrize(
    "timezone", ["America/Atlantida", "GMT-3 Brasília", "../etc/passwd", "America", "Etc"]
)
def test_reporting_period_unknown_timezone_is_rejected(timezone: str) -> None:
    with pytest.raises(ValidationError, match="timezone"):
        ReportingPeriod.model_validate(
            {
                "start": "2026-10-01",
                "end": "2026-10-31",
                "timezone": timezone,
                "periodicity": "monthly",
            }
        )


# --- TaskProfile / allowlist ---


def test_profile_with_formal_tool_is_rejected() -> None:
    # Arrange
    registry = dict(MVP_TOOLS) | {"formal_approve_report": PermissionLevel.FORMAL}
    data = {
        "kind": TaskKind.RESEARCH_REPORT,
        "prompt_version": "v1",
        "allowed_tools": frozenset({"ledger_query_events", "formal_approve_report"}),
        "output_schema": ResearchReportDraft,
    }

    # Act / Assert
    with pytest.raises(ValidationError, match="nível não permitido"):
        TaskProfile.model_validate(data, context={TOOL_REGISTRY_CONTEXT_KEY: registry})


def test_profile_with_unknown_tool_is_rejected() -> None:
    with pytest.raises(ValidationError, match="desconhecidas"):
        TaskProfile(
            kind=TaskKind.RESEARCH_REPORT,
            prompt_version="v1",
            allowed_tools=frozenset({"shell_exec"}),
            output_schema=ResearchReportDraft,
        )


def test_research_report_profile_has_no_external_or_formal_tools() -> None:
    # Act
    levels = {MVP_TOOLS[name] for name in RESEARCH_REPORT_PROFILE.allowed_tools}

    # Assert
    assert levels <= {PermissionLevel.READ, PermissionLevel.WRITE_INTERNAL}
    assert RESEARCH_REPORT_PROFILE.output_schema is ResearchReportDraft


@pytest.mark.parametrize(
    "kind", [kind for kind in TaskKind if kind is not TaskKind.RESEARCH_REPORT]
)
def test_get_profile_without_executable_profile_fails(kind: TaskKind) -> None:
    with pytest.raises(ProfileNotAvailableError):
        get_profile(kind)


def test_research_report_prompt_v1_loads_with_core_rules() -> None:
    # Act
    prompt = load_prompt(get_profile(TaskKind.RESEARCH_REPORT))

    # Assert
    assert "untrusted_data" in prompt
    assert "FORMAL_HOURS_DECLARED" in prompt
    assert "potencialmente qualificável, sujeito a análise" in prompt
    for tool in RESEARCH_REPORT_PROFILE.allowed_tools:
        assert f"`{tool}`" in prompt
    for tool in set(MVP_TOOLS) - RESEARCH_REPORT_PROFILE.allowed_tools:
        assert tool not in prompt


# --- RunStatus / AgentRun ---


@pytest.mark.parametrize("terminal", TERMINAL_STATUSES)
def test_terminal_run_statuses_have_no_exit(terminal: RunStatus) -> None:
    assert all(not can_transition(terminal, target) for target in RunStatus)


def test_running_can_return_to_queued_for_retry() -> None:
    assert can_transition(RunStatus.RUNNING, RunStatus.QUEUED)
    assert not can_transition(RunStatus.QUEUED, RunStatus.COMPLETED)


def test_every_run_status_has_declared_transitions() -> None:
    assert set(ALLOWED_TRANSITIONS) == set(RunStatus)


def test_failed_run_without_error_is_rejected() -> None:
    with pytest.raises(ValidationError, match="failed exige error"):
        AgentRun(**run_kwargs(status=RunStatus.FAILED, attempts=1))


def test_running_run_without_attempt_is_rejected() -> None:
    with pytest.raises(ValidationError, match="ao menos uma tentativa"):
        AgentRun(**run_kwargs(status=RunStatus.RUNNING, attempts=0))


def test_run_attempts_above_max_is_rejected() -> None:
    with pytest.raises(ValidationError, match="max_attempts"):
        AgentRun(**run_kwargs(attempts=4, max_attempts=3))


@pytest.mark.parametrize("key", ["curta", "chave com espaço!", "-começa-com-hífen"])
def test_run_invalid_idempotency_key_is_rejected(key: str) -> None:
    with pytest.raises(ValidationError):
        AgentRun(**run_kwargs(idempotency_key=key))


def test_run_updated_before_created_is_rejected() -> None:
    # Arrange
    created = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)

    # Act / Assert
    with pytest.raises(ValidationError, match="updated_at"):
        AgentRun(**run_kwargs(created_at=created, updated_at=created - timedelta(seconds=1)))


AT = datetime(2026, 11, 7, 12, 5, tzinfo=UTC)
RETRYABLE = RunError(code="provider_timeout", message="Maker sem resposta.", retryable=True)
FATAL = RunError(code="invalid_output", message="Saída fora do schema.", retryable=False)


def test_transition_run_counts_attempt_when_running() -> None:
    # Arrange
    run = AgentRun(**run_kwargs())

    # Act
    running = transition_run(run, RunStatus.RUNNING, at=AT)

    # Assert
    assert running.status is RunStatus.RUNNING
    assert running.attempts == 1
    assert running.updated_at == AT


def test_transition_run_rejects_disallowed_transition() -> None:
    # Arrange
    run = AgentRun(**run_kwargs())

    # Act / Assert
    with pytest.raises(InvalidRunTransitionError):
        transition_run(run, RunStatus.COMPLETED, at=AT)


def test_fail_or_retry_requeues_retryable_error_with_attempts_left() -> None:
    # Arrange
    run = AgentRun(**run_kwargs(status=RunStatus.RUNNING, attempts=1))

    # Act
    result = fail_or_retry(run, RETRYABLE, at=AT)

    # Assert
    assert result.status is RunStatus.QUEUED
    assert result.error == RETRYABLE


@pytest.mark.parametrize(("attempts", "error"), [(3, RETRYABLE), (1, FATAL)])
def test_fail_or_retry_fails_when_exhausted_or_not_retryable(
    attempts: int, error: RunError
) -> None:
    # Arrange
    run = AgentRun(**run_kwargs(status=RunStatus.RUNNING, attempts=attempts))

    # Act
    result = fail_or_retry(run, error, at=AT)

    # Assert
    assert result.status is RunStatus.FAILED
    assert result.error == error


def test_queued_run_with_non_retryable_error_is_rejected() -> None:
    with pytest.raises(ValidationError, match="retryable"):
        AgentRun(**run_kwargs(attempts=1, error=FATAL))


def test_awaiting_input_run_with_error_is_rejected() -> None:
    with pytest.raises(ValidationError, match="awaiting_input"):
        AgentRun(**run_kwargs(status=RunStatus.AWAITING_INPUT, attempts=1, error=RETRYABLE))


def test_failed_run_with_error_is_accepted() -> None:
    # Arrange
    error = RunError(code="provider_timeout", message="Checker sem resposta.", retryable=True)

    # Act
    run = AgentRun(**run_kwargs(status=RunStatus.FAILED, attempts=3, error=error))

    # Assert
    assert run.error is not None
    assert run.error.retryable is True
