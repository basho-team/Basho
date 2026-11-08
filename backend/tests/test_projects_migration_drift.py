"""Garante que os CHECKs congelados da migração 0005 acompanham os enums do contrato (#5)."""

import importlib.util
from pathlib import Path
from typing import Any

from basho.compliance.api_contracts import ApprovalDecision, PendingKind
from basho.identity import HumanRole

MIGRATION = Path(__file__).resolve().parents[1] / "migrations" / "versions" / "0005_projects.py"


def _load_migration() -> Any:
    spec = importlib.util.spec_from_file_location("migration_0005", MIGRATION)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_check_values_match_contract_enums() -> None:
    # Arrange / Act
    migration = _load_migration()

    # Assert
    assert set(migration._PENDING_KINDS) == {value.value for value in PendingKind}
    assert set(migration._APPROVAL_DECISIONS) == {value.value for value in ApprovalDecision}
    assert set(migration._ANSWER_ROLES) == {value.value for value in HumanRole}
