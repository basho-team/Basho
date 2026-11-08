"""Helpers sintéticos para os testes de relatórios (dados fictícios, `is_synthetic`)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from basho.agent.artifacts import ResearchReportDraft
from basho.reports.versions import ReportVersion

FIXTURES = Path(__file__).parent / "fixtures"
TENANT = UUID("99999999-9999-4999-8999-999999999999")
RESEARCHER_ANA = UUID("33333333-3333-4333-8333-333333333333")
MANAGER = UUID("55555555-5555-4555-8555-555555555555")
T0 = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


def load_draft(name: str) -> ResearchReportDraft:
    data = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    data.pop("_synthetic", None)
    return ResearchReportDraft.model_validate(data)


def first_version(name: str = "research_report_draft.json") -> ReportVersion:
    return ReportVersion(
        id=uuid4(),
        tenant_id=TENANT,
        number=1,
        draft=load_draft(name),
        created_at=T0,
        is_synthetic=True,
    )


def at(minutes: int) -> datetime:
    return T0 + timedelta(minutes=minutes)
