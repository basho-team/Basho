"""Garante que os CHECKs congelados da migração 0004 acompanham os enums de audit e agent."""

import importlib.util
from pathlib import Path
from typing import Any

from basho.agent.approvals import ApprovalDecision
from basho.agent.tools import PermissionLevel
from basho.audit import ActorType, AuditDecision, AuditEventType, AuditOutcome

MIGRATION = Path(__file__).resolve().parents[1] / "migrations" / "versions" / "0004_tool_audit.py"


def _load_migration() -> Any:
    spec = importlib.util.spec_from_file_location("migration_0004", MIGRATION)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_check_values_match_contract_enums() -> None:
    # Arrange / Act
    migration = _load_migration()

    # Assert
    assert set(migration._EVENT_TYPES) == {value.value for value in AuditEventType}
    assert set(migration._ACTOR_TYPES) == {value.value for value in ActorType}
    assert set(migration._LEVELS) == {value.value for value in PermissionLevel}
    assert set(migration._DECISIONS) == {value.value for value in AuditDecision}
    assert set(migration._OUTCOMES) == {value.value for value in AuditOutcome}
    assert set(migration._APPROVAL_DECISIONS) == {value.value for value in ApprovalDecision}
