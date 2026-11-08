"""Garante que os CHECKs congelados da migração 0001 acompanham os enums do contrato."""

import importlib.util
from pathlib import Path

from basho.evidence.contracts import EventKind, EventSource

MIGRATION = (
    Path(__file__).resolve().parents[1] / "migrations" / "versions" / "0001_evidence_events.py"
)


def _load_migration() -> object:
    spec = importlib.util.spec_from_file_location("migration_0001", MIGRATION)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_kinds_and_sources_match_contract_enums() -> None:
    migration = _load_migration()

    assert set(migration._KINDS) == {kind.value for kind in EventKind}  # type: ignore[attr-defined]
    assert set(migration._SOURCES) == {source.value for source in EventSource}  # type: ignore[attr-defined]
