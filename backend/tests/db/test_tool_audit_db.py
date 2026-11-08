"""Integração do audit log e das aprovações com Postgres (migração 0004)."""

from uuid import UUID, uuid4

import psycopg
import pytest
from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from basho.agent.approvals import (
    ApprovalAlreadyDecidedError,
    ApprovalDecision,
    ApprovalNotFoundError,
    ApprovalState,
    NewApprovalRequest,
    PostgresApprovalStore,
    decide_approval,
)
from basho.agent.policy import ToolCallContext, ToolPolicy
from basho.agent.registry import ToolRegistry
from basho.agent.simulated_tools import GithubCreateIssue
from basho.agent.tasks import RESEARCH_REPORT_PROFILE
from basho.agent.tools import PermissionLevel, ToolCallStatus
from basho.audit import (
    ActorType,
    AuditDecision,
    AuditError,
    AuditEventType,
    AuditOutcome,
    AuditService,
    InputSummary,
    NewAuditEntry,
)
from basho.db import tenant_session
from db_support import run_alembic, run_alembic_raw

pytestmark = pytest.mark.db

Factory = async_sessionmaker[AsyncSession]
APPEND_ONLY = "append-only"


def _entry(tenant_id: UUID, run_id: UUID, **overrides: object) -> NewAuditEntry:
    values: dict[str, object] = {
        "tenant_id": tenant_id,
        "event_type": AuditEventType.TOOL_CALL,
        "actor_type": ActorType.AGENT,
        "run_id": run_id,
        "tool": "github_list_commits",
        "level": PermissionLevel.READ,
        "decision": AuditDecision.ALLOWED,
        "outcome": AuditOutcome.OK,
        "input_summary": InputSummary(keys=("limit",), size_bytes=12),
    }
    return NewAuditEntry.model_validate(values | overrides)


def _request(tenant_id: UUID) -> NewApprovalRequest:
    return NewApprovalRequest(
        tenant_id=tenant_id,
        run_id=uuid4(),
        tool="github_create_issue",
        level=PermissionLevel.EXTERNAL,
        arguments={"title": "titulo", "body": "corpo"},
    )


async def test_audit_entry_roundtrips_and_lists_by_run(session_factory: Factory) -> None:
    # Arrange
    tenant_id, run_id = uuid4(), uuid4()
    entry = _entry(tenant_id, run_id)

    # Act
    async with tenant_session(session_factory, tenant_id) as session:
        saved = await AuditService(session).record(entry)
    async with tenant_session(session_factory, tenant_id) as session:
        listed = await AuditService(session).list_for_run(tenant_id, run_id)

    # Assert
    assert listed == [saved]
    assert saved.model_dump(exclude={"id", "created_at"}) == entry.model_dump()


async def test_unknown_tool_entry_with_null_level_is_persisted(session_factory: Factory) -> None:
    # Arrange
    tenant_id = uuid4()
    entry = _entry(
        tenant_id,
        uuid4(),
        tool="unknown_tool",
        level=None,
        decision=AuditDecision.DENIED,
        outcome=AuditOutcome.NOT_EXECUTED,
        reason_code="unknown_tool",
    )

    # Act
    async with tenant_session(session_factory, tenant_id) as session:
        saved = await AuditService(session).record(entry)

    # Assert
    assert saved.level is None


async def test_audit_refuses_session_of_another_tenant(session_factory: Factory) -> None:
    # Arrange
    entry = _entry(uuid4(), uuid4())

    # Act / Assert
    with pytest.raises(AuditError):
        async with tenant_session(session_factory, uuid4()) as session:
            await AuditService(session).record(entry)


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE audit_log SET outcome = 'error' WHERE tenant_id = :t",
        "DELETE FROM audit_log WHERE tenant_id = :t",
        "UPDATE tool_approval_requests SET tool = 'other_tool' WHERE tenant_id = :t",
        "DELETE FROM tool_approval_requests WHERE tenant_id = :t",
        "DELETE FROM tool_approval_decisions WHERE tenant_id = :t",
    ],
)
async def test_mutations_are_rejected_by_trigger(session_factory: Factory, statement: str) -> None:
    # Arrange
    tenant_id = uuid4()
    async with tenant_session(session_factory, tenant_id) as session:
        await AuditService(session).record(_entry(tenant_id, uuid4()))
        store = PostgresApprovalStore(session)
        request = await store.create(_request(tenant_id))
        await store.decide(tenant_id, request.id, ApprovalDecision.REJECTED, uuid4())

    # Act / Assert
    with pytest.raises(DBAPIError, match=APPEND_ONLY):
        async with tenant_session(session_factory, tenant_id) as session:
            await session.execute(text(statement), {"t": tenant_id})


async def test_app_role_cannot_alter_audit_log(session_factory: Factory) -> None:
    # Arrange
    tenant_id = uuid4()
    async with tenant_session(session_factory, tenant_id) as session:
        await AuditService(session).record(_entry(tenant_id, uuid4()))

    # Act / Assert: privilégio negado antes mesmo do trigger
    with pytest.raises(DBAPIError, match="permission denied"):
        async with tenant_session(session_factory, tenant_id) as session:
            await session.execute(text("SET LOCAL ROLE basho_api"))
            await session.execute(text("UPDATE audit_log SET outcome = 'error'"))


async def test_rls_hides_other_tenants_rows_from_app_role(session_factory: Factory) -> None:
    # Arrange
    tenant_a, tenant_b, run_id = uuid4(), uuid4(), uuid4()
    async with tenant_session(session_factory, tenant_b) as session:
        await AuditService(session).record(_entry(tenant_b, run_id))

    # Act
    async with tenant_session(session_factory, tenant_a) as session:
        await session.execute(text("SET LOCAL ROLE basho_api"))
        visible = (
            await session.execute(
                text("SELECT count(*) FROM audit_log WHERE run_id = :r"), {"r": run_id}
            )
        ).scalar_one()
        with pytest.raises(DBAPIError, match="row-level security"):
            async with session.begin_nested():
                await session.execute(
                    text(
                        "INSERT INTO audit_log (id, tenant_id, event_type, actor_type, run_id, "
                        "tool, level, decision, outcome, input_size_bytes) VALUES (:id, :t, "
                        "'tool_call', 'agent', :r, 'github_list_commits', 'read', 'allowed', "
                        "'ok', 0)"
                    ),
                    {"id": uuid4(), "t": tenant_b, "r": run_id},
                )

    # Assert
    assert visible == 0


async def test_approval_is_decided_once_and_state_is_derived(session_factory: Factory) -> None:
    # Arrange
    tenant_id, reviewer = uuid4(), uuid4()
    async with tenant_session(session_factory, tenant_id) as session:
        request = await PostgresApprovalStore(session).create(_request(tenant_id))

    # Act
    async with tenant_session(session_factory, tenant_id) as session:
        store = PostgresApprovalStore(session)
        pending = await store.get(tenant_id, request.id)
        approved = await decide_approval(
            store,
            AuditService(session),
            tenant_id=tenant_id,
            approval_id=request.id,
            decision=ApprovalDecision.APPROVED,
            decided_by=reviewer,
        )

    # Assert
    assert pending.state is ApprovalState.PENDING
    assert (approved.state, approved.decided_by) == (ApprovalState.APPROVED, reviewer)
    with pytest.raises(ApprovalAlreadyDecidedError):
        async with tenant_session(session_factory, tenant_id) as session:
            await PostgresApprovalStore(session).decide(
                tenant_id, request.id, ApprovalDecision.REJECTED, reviewer
            )
    async with tenant_session(session_factory, tenant_id) as session:
        entries = await AuditService(session).list_for_run(tenant_id, request.run_id)
    assert [e.decision for e in entries] == [AuditDecision.APPROVED]


async def test_approval_of_another_tenant_is_not_found(session_factory: Factory) -> None:
    # Arrange
    owner = uuid4()
    async with tenant_session(session_factory, owner) as session:
        request = await PostgresApprovalStore(session).create(_request(owner))
    intruder = uuid4()

    # Act / Assert
    with pytest.raises(ApprovalNotFoundError):
        async with tenant_session(session_factory, intruder) as session:
            await PostgresApprovalStore(session).get(intruder, request.id)


async def test_policy_persists_pending_external_call_and_audit(session_factory: Factory) -> None:
    # Arrange
    tool = GithubCreateIssue()
    registry = ToolRegistry([tool])
    profile = RESEARCH_REPORT_PROFILE.model_copy(
        update={"allowed_tools": frozenset({"github_create_issue"})}
    )
    context = ToolCallContext(tenant_id=uuid4(), run_id=uuid4(), profile=profile)

    # Act
    async with tenant_session(session_factory, context.tenant_id) as session:
        policy = ToolPolicy(registry, AuditService(session), PostgresApprovalStore(session))
        result = await policy.execute(
            context, "github_create_issue", {"title": "titulo", "body": "corpo"}
        )

    # Assert
    assert result.status is ToolCallStatus.PENDING_APPROVAL
    assert result.approval_id is not None
    assert tool.created == []
    async with tenant_session(session_factory, context.tenant_id) as session:
        view = await PostgresApprovalStore(session).get(context.tenant_id, UUID(result.approval_id))
        (entry,) = await AuditService(session).list_for_run(context.tenant_id, context.run_id)
    assert view.state is ApprovalState.PENDING
    assert entry.approval_id == view.request.id


def test_downgrade_is_refused_when_audit_log_has_rows(migration_db_url: URL) -> None:
    # Arrange
    run_alembic(migration_db_url, "upgrade", "head")
    dsn = migration_db_url.set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(dsn) as connection:
        connection.execute(
            "INSERT INTO audit_log (id, tenant_id, event_type, actor_type, run_id, tool, level, "
            "decision, outcome, input_size_bytes) VALUES (gen_random_uuid(), gen_random_uuid(), "
            "'tool_call', 'agent', gen_random_uuid(), 'github_list_commits', 'read', 'allowed', "
            "'ok', 0)"
        )

    # Act
    result = run_alembic_raw(migration_db_url, "downgrade", "0001")

    # Assert
    assert result.returncode != 0
    assert APPEND_ONLY in result.stderr
