"""Garante que os CHECKs congelados da migração 0008 acompanham os enums do contrato (ADR-0010)."""

import importlib.util
from pathlib import Path
from typing import Any

from basho.publishing.contracts import LinkStatus, PublicationStatus
from basho.publishing.links import LinkKind

MIGRATION = Path(__file__).resolve().parents[1] / "migrations" / "versions" / "0008_publishing.py"


def _load_migration() -> Any:
    spec = importlib.util.spec_from_file_location("migration_0008", MIGRATION)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_check_values_match_contract_enums() -> None:
    # Arrange / Act
    migration = _load_migration()

    # Assert
    assert set(migration._LINK_KINDS) == {value.value for value in LinkKind}
    assert set(migration._LINK_STATUSES) == {value.value for value in LinkStatus}
    assert set(migration._PUBLICATION_STATUSES) == {value.value for value in PublicationStatus}
