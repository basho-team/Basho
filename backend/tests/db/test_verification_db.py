"""O resultado do Checker entra no ledger como evento VERIFICATION_RESULT (ADR-0003/0004)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from basho.agent.checker import VerificationOutcome, verification_event
from basho.agent.verifier import Verdict, VerificationResult
from basho.db import tenant_session
from basho.evidence import EvidenceService
from basho.evidence.contracts import ArtifactStatus, EventKind
from evidence_factories import fresh_ids, make_event

pytestmark = pytest.mark.db


async def test_verification_result_is_appended_and_readable(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Arrange
    tenant_id, project_id = fresh_ids()
    outcome = VerificationOutcome(
        status=ArtifactStatus.VERIFIED,
        deterministic=VerificationResult(verdict=Verdict.PASS, checker="deterministic"),
        checker=VerificationResult(verdict=Verdict.PASS, checker="provider/checker-model"),
    )
    async with tenant_session(session_factory, tenant_id) as session:
        artifact = await EvidenceService(session).append(
            make_event(tenant_id=tenant_id, project_id=project_id)
        )

    # Act
    event = verification_event(
        tenant_id=tenant_id,
        project_id=project_id,
        artifact_event_id=artifact.id,
        outcome=outcome,
        is_synthetic=True,
    )
    async with tenant_session(session_factory, tenant_id) as session:
        saved = await EvidenceService(session).append(event)
    async with tenant_session(session_factory, tenant_id) as session:
        loaded = await EvidenceService(session).get(tenant_id, saved.id)

    # Assert
    assert loaded.kind is EventKind.VERIFICATION_RESULT
    assert loaded.actor.model == "provider/checker-model"
    assert loaded.payload["status"] == "verified"
    assert loaded.payload["checker"]["verdict"] == "pass"
