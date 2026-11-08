"""Casos de avaliação sintéticos do perfil research_report: schema e coerência dos dados.

Só verifica o que já existe (schema de #41) e a integridade dos casos. As violações esperadas
são insumo para os checks de #9 e as evals de #24, não implementadas aqui.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from basho.agent.artifacts import ResearchReportDraft

CASES_DIR = Path(__file__).parent / "fixtures" / "reports" / "eval_cases"
KNOWN_VIOLATIONS = frozenset(
    {
        "negative_result_omitted",
        "formal_data_in_text",
        "eligibility_assertion",
        "unknown_evidence",
        "formal_hours_not_formal",
        "followed_untrusted_instruction",
        "unsupported_by_evidence",
    }
)
CASES = sorted(CASES_DIR.glob("*.json"))


def _load(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def test_cases_exist_and_cover_every_violation_code() -> None:
    covered = {v for p in CASES for v in _load(p)["expected"]["check_violations"]}
    assert len(CASES) >= 10
    assert covered == KNOWN_VIOLATIONS


@pytest.mark.parametrize("path", CASES, ids=lambda p: p.stem)
def test_case_is_synthetic_and_well_formed(path: Path) -> None:
    case = _load(path)
    assert case["_synthetic"] is True
    assert case["case_id"] == path.stem
    assert set(case["expected"]["check_violations"]) <= KNOWN_VIOLATIONS
    ids = [e["id"] for e in case["ledger_context"]]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("path", CASES, ids=lambda p: p.stem)
def test_schema_validity_matches_expectation(path: Path) -> None:
    case = _load(path)
    if case["expected"]["schema_valid"]:
        ResearchReportDraft.model_validate(case["draft"])
        return
    assert not case["expected"]["check_violations"], "schema-inválido não chega aos checks"
    with pytest.raises(ValidationError, match=case["expected"]["schema_error_contains"]):
        ResearchReportDraft.model_validate(case["draft"])


@pytest.mark.parametrize("path", CASES, ids=lambda p: p.stem)
def test_cases_without_unknown_evidence_cite_only_ledger_ids(path: Path) -> None:
    case = _load(path)
    if "unknown_evidence" in case["expected"]["check_violations"]:
        return
    ledger = {e["id"] for e in case["ledger_context"]}
    draft = case["draft"]
    cited = {eid for c in draft["claims"] for eid in c.get("evidence_ids", [])}
    cited |= {eid for x in draft["experiments"] for eid in x["evidence_ids"]}
    cited |= set(draft["formal_hours_event_ids"])
    assert cited <= ledger
