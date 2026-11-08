"""Garante que os CHECKs congelados das migrações acompanham os enums do contrato.

A 0009 redefiniu os CHECKs de kind/source do ledger; é ela que precisa espelhar os enums.
"""

import importlib.util
from pathlib import Path

from basho.evidence.contracts import EventKind, EventSource

MIGRATION = (
    Path(__file__).resolve().parents[1] / "migrations" / "versions" / "0001_evidence_events.py"
)
LEDGER_CHECKS = MIGRATION.with_name("0009_document_sources.py")


def _load_migration() -> object:
    spec = importlib.util.spec_from_file_location("migration_0009", LEDGER_CHECKS)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_kinds_and_sources_match_contract_enums() -> None:
    migration = _load_migration()

    assert set(migration._KINDS) == {kind.value for kind in EventKind}  # type: ignore[attr-defined]
    assert set(migration._SOURCES) == {source.value for source in EventSource}  # type: ignore[attr-defined]


def test_reports_migration_enums_match_domain_enums() -> None:
    from basho.agent.artifacts import Periodicity
    from basho.reports import ReviewDecision, ReviewerRole

    path = MIGRATION.with_name("0003_reports.py")
    spec = importlib.util.spec_from_file_location("migration_0003", path)
    assert spec is not None
    assert spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    assert set(migration._PERIODICITIES) == {item.value for item in Periodicity}
    assert set(migration._REVIEWER_ROLES) == {item.value for item in ReviewerRole}
    assert set(migration._DECISIONS) == {item.value for item in ReviewDecision}
