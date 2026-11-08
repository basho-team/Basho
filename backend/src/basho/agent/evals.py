"""Evals dos checks determinísticos contra os casos sintéticos de relatório (#24).

Os casos (`tests/fixtures/reports/eval_cases/*.json`) trazem `ledger_context`, um `draft` e as
violações esperadas. Aqui o contexto vira `EvidenceEvent` em memória e o draft passa pelo
`ReportDeterministicChecker`. Violações que só o Checker LLM detecta ficam fora do escopo
determinístico e aparecem como tal no relatório, sem contar como erro.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from basho.agent.artifacts import ResearchReportDraft
from basho.agent.checks import (
    ELIGIBILITY_ASSERTION,
    FORMAL_DATA_IN_TEXT,
    FORMAL_HOURS_NOT_FORMAL,
    PROMPT_INJECTION,
    UNKNOWN_EVIDENCE,
    ReportDeterministicChecker,
)
from basho.evidence.contracts import (
    Actor,
    ActorType,
    EventKind,
    EventSource,
    EvidenceEvent,
    NewEvidenceEvent,
)
from basho.evidence.domain.hashing import compute_content_hash

EVAL_TENANT = UUID("00000000-0000-4000-8000-00000000e7a1")

CODE_ALIASES = {PROMPT_INJECTION: "followed_untrusted_instruction"}
"""Código do check → vocabulário dos casos (README dos eval cases, PR #43)."""

DETERMINISTIC_CODES = frozenset(
    {
        UNKNOWN_EVIDENCE,
        FORMAL_HOURS_NOT_FORMAL,
        FORMAL_DATA_IN_TEXT,
        ELIGIBILITY_ASSERTION,
        "followed_untrusted_instruction",
    }
)
"""Violações que os checks determinísticos devem pegar; as demais são do Checker LLM."""

_KIND_MAP = {
    "COMMIT": (EventKind.COMMIT_OBSERVED, EventSource.GITHUB),
    "PR_OPENED": (EventKind.PULL_REQUEST_OBSERVED, EventSource.GITHUB),
    "PR_MERGED": (EventKind.PULL_REQUEST_OBSERVED, EventSource.GITHUB),
    "FORMAL_HOURS_DECLARED": (EventKind.FORMAL_HOURS_DECLARED, EventSource.USER),
}


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    schema_valid: bool
    expected: frozenset[str]
    detected: frozenset[str]

    @property
    def expected_deterministic(self) -> frozenset[str]:
        return self.expected & DETERMINISTIC_CODES

    @property
    def missed(self) -> frozenset[str]:
        return self.expected_deterministic - self.detected

    @property
    def false_alarms(self) -> frozenset[str]:
        return self.detected - self.expected

    @property
    def llm_only(self) -> frozenset[str]:
        return self.expected - DETERMINISTIC_CODES

    @property
    def passed(self) -> bool:
        return not self.missed and not self.false_alarms


@dataclass(frozen=True)
class EvalSummary:
    results: tuple[CaseResult, ...]
    true_positives: int = field(init=False)
    expected_total: int = field(init=False)
    detected_total: int = field(init=False)

    def __post_init__(self) -> None:
        tp = sum(len(r.expected_deterministic & r.detected) for r in self.results)
        object.__setattr__(self, "true_positives", tp)
        object.__setattr__(
            self, "expected_total", sum(len(r.expected_deterministic) for r in self.results)
        )
        object.__setattr__(self, "detected_total", sum(len(r.detected) for r in self.results))

    @property
    def recall(self) -> float:
        return self.true_positives / self.expected_total if self.expected_total else 1.0

    @property
    def precision(self) -> float:
        return self.true_positives / self.detected_total if self.detected_total else 1.0


def load_case(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def case_evidence(case: dict[str, Any], project_id: UUID) -> list[EvidenceEvent]:
    """`ledger_context` → eventos persistidos em memória (o `summary` é dado de fonte)."""
    events = []
    for item in case["ledger_context"]:
        kind, source = _KIND_MAP[item["kind"]]
        actor = (
            Actor(type=ActorType.USER, id="eval-user")
            if source is EventSource.USER
            else Actor(type=ActorType.SYSTEM, id="eval-connector")
        )
        new = NewEvidenceEvent(
            tenant_id=EVAL_TENANT,
            project_id=project_id,
            kind=kind,
            source=source,
            source_ref=item["source_ref"],
            actor=actor,
            payload={"summary": item["summary"]},
            is_synthetic=True,
        )
        events.append(
            EvidenceEvent(
                **new.model_dump(),
                id=UUID(item["id"]),
                content_hash=compute_content_hash(new),
                created_at=datetime.now(UTC),
            )
        )
    return events


def run_case(case: dict[str, Any]) -> CaseResult:
    expected = frozenset(case["expected"]["check_violations"])
    try:
        draft = ResearchReportDraft.model_validate(case["draft"])
    except ValidationError:
        return CaseResult(case["case_id"], False, expected, frozenset())
    evidence = case_evidence(case, draft.project_id)
    result = ReportDeterministicChecker(EVAL_TENANT).check(draft, evidence)
    detected = frozenset(CODE_ALIASES.get(issue.code, issue.code) for issue in result.issues)
    return CaseResult(case["case_id"], True, expected, detected)


def run_cases(paths: Iterable[Path]) -> EvalSummary:
    return EvalSummary(tuple(run_case(load_case(path)) for path in sorted(paths)))


def render_report(summary: EvalSummary) -> str:
    """Relatório em Markdown para o PR e para a demo."""
    lines = [
        "# Evals dos checks determinísticos (#24)",
        "",
        f"- Casos: {len(summary.results)} "
        f"(barrados pelo schema: {sum(not r.schema_valid for r in summary.results)})",
        f"- Recall determinístico: {summary.recall:.0%} "
        f"({summary.true_positives}/{summary.expected_total})",
        f"- Precisão: {summary.precision:.0%} ({summary.true_positives}/{summary.detected_total})",
        "",
        "| Caso | Schema | Esperado | Detectado | Só Checker LLM | Resultado |",
        "|---|---|---|---|---|---|",
    ]
    for r in summary.results:
        lines.append(
            f"| `{r.case_id}` | {'ok' if r.schema_valid else 'barrado'} "
            f"| {_codes(r.expected_deterministic)} | {_codes(r.detected)} "
            f"| {_codes(r.llm_only)} | {'ok' if r.passed else 'FALHOU'} |"
        )
    return "\n".join(lines) + "\n"


def _codes(codes: Sequence[str] | frozenset[str]) -> str:
    return ", ".join(f"`{c}`" for c in sorted(codes)) or "—"


DEFAULT_CASES_DIR = (
    Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "reports" / "eval_cases"
)


def main(argv: Sequence[str] | None = None) -> int:
    """`uv run python -m basho.agent.evals [pasta-dos-casos]`; sai com 1 se algum caso falhar.

    A pasta padrão fica em `backend/tests/fixtures` (só existe no checkout do repositório).
    """
    args = sys.argv[1:] if argv is None else list(argv)
    cases_dir = Path(args[0]) if args else DEFAULT_CASES_DIR
    summary = run_cases(cases_dir.glob("*.json"))
    sys.stdout.write(render_report(summary))
    return 0 if all(r.passed for r in summary.results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
