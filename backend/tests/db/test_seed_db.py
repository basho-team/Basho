"""Seed sintético da demonstração (#14): projeto, evidências, vereditos e pendências derivadas."""

from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from basho.db import tenant_session
from basho.evidence import EvidenceService
from basho.evidence.contracts import FORMAL_DATA_KINDS
from basho.projects import ProjectService
from basho.seed import seed_demo
from evidence_factories import fresh_ids

pytestmark = pytest.mark.db

Factory = async_sessionmaker[AsyncSession]


async def _seed(factory: Factory, tenant_id: UUID) -> dict[str, str]:
    async with tenant_session(factory, tenant_id) as session:
        return await seed_demo(session, tenant_id)


async def test_seed_creates_a_synthetic_project_with_pending_work(
    session_factory: Factory,
) -> None:
    # Arrange
    tenant_id, _ = fresh_ids()

    # Act
    result = await _seed(session_factory, tenant_id)

    # Assert: projeto sintético com duas atividades
    project_id = UUID(result["project_id"])
    assert result["created"] == "true"
    async with tenant_session(session_factory, tenant_id) as session:
        service = ProjectService(session)
        project = await service.get_project(tenant_id, project_id)
        page = await service.list_pending(tenant_id, project_id, status=None, limit=50, offset=0)
    assert project.is_synthetic is True
    assert len(project.activities) == 2
    # aprovação do gerente + divergência do Checker + 2 lacunas do Maker
    kinds = sorted(item.kind for item in page.items)
    assert kinds == [
        "approval_required",
        "checker_disagreement",
        "missing_justification",
        "missing_justification",
    ]


async def test_seed_never_records_formal_data_and_marks_everything_synthetic(
    session_factory: Factory,
) -> None:
    # Arrange
    tenant_id, _ = fresh_ids()

    # Act
    result = await _seed(session_factory, tenant_id)

    # Assert: nenhum evento formal (horas, participantes) e tudo sintético (regras 6 e 9)
    async with tenant_session(session_factory, tenant_id) as session:
        events = await EvidenceService(session).query(
            tenant_id, project_id=UUID(result["project_id"])
        )
    assert not {event.kind for event in events} & FORMAL_DATA_KINDS
    assert events
    assert all(event.is_synthetic for event in events)


async def test_seed_is_idempotent(session_factory: Factory) -> None:
    # Arrange
    tenant_id, _ = fresh_ids()
    first = await _seed(session_factory, tenant_id)

    # Act
    second = await _seed(session_factory, tenant_id)

    # Assert
    assert second == {"project_id": first["project_id"], "created": "false"}
