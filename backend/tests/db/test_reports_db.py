"""Persistência de reports com Postgres real: versões, revisão exata, RLS e append-only."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from basho.db import tenant_session
from basho.evidence import EvidenceService
from basho.evidence.contracts import Actor, ActorType, EventKind, EventSource
from basho.reports import (
    ReportAlreadyExistsError,
    ReportNotFoundError,
    ReportService,
    ReportValidationError,
    ReviewDecision,
    ReviewerNotAllowedError,
    ReviewerRole,
    VersionConflictError,
)
from basho.reports.consolidation import ReviewState
from basho.reports.corrections import ReviseClaim
from basho.reports.schemas import CorrectionIn, ReportVersionOut, ReviewIn, ReviewOut
from evidence_factories import fresh_ids, make_event
from report_db_factories import MAKER, RESEARCHER, seed_draft, seed_report

pytestmark = pytest.mark.db

Factory = async_sessionmaker[AsyncSession]
MANAGER = UUID("55555555-5555-4555-8555-555555555555")
PENDING_CLAIM = 3
REPORT_TABLES = ("reporting_periods", "report_versions", "report_reviews")
APPROVE = ReviewIn(decision=ReviewDecision.TEXT_APPROVED)


def _correction(v1: ReportVersionOut) -> ReviewIn:
    """Resolve o claim `pending` do fixture citando a primeira evidência do relatório."""
    op = ReviseClaim(
        claim_id=v1.version.claim_ids[PENDING_CLAIM],
        text="Hipótese registrada: SMOTE reduz o viés de classe sem perda de recall.",
        status="supported",
        evidence_ids=(v1.version.draft.claims[0].evidence_ids[0],),
    )
    return ReviewIn(
        decision=ReviewDecision.CHANGES_REQUESTED,
        comment="Hipótese do rebalanceamento estava sem registro.",
        correction=CorrectionIn(reason="Pesquisador registrou a hipótese.", operations=(op,)),
    )


async def _review(
    factory: Factory,
    tenant_id: UUID,
    version_id: UUID,
    body: ReviewIn,
    *,
    reviewer_id: UUID = RESEARCHER,
    reviewer_role: ReviewerRole = ReviewerRole.RESEARCHER,
) -> ReviewOut:
    async with tenant_session(factory, tenant_id) as session:
        return await ReportService(session).review(
            tenant_id, version_id, body, reviewer_id=reviewer_id, reviewer_role=reviewer_role
        )


async def _get(factory: Factory, tenant_id: UUID, version_id: UUID) -> ReportVersionOut:
    async with tenant_session(factory, tenant_id) as session:
        return await ReportService(session).get_version(tenant_id, version_id)


async def _count_reviews(factory: Factory, tenant_id: UUID) -> int:
    async with tenant_session(factory, tenant_id) as session:
        result = await session.execute(
            text("SELECT count(*) FROM report_reviews WHERE tenant_id = :t"), {"t": tenant_id}
        )
        return int(result.scalar_one())


async def _new_report(factory: Factory) -> tuple[UUID, ReportVersionOut]:
    tenant_id, project_id = fresh_ids()
    async with tenant_session(factory, tenant_id) as session:
        _, created = await seed_report(session, tenant_id, project_id)
    return tenant_id, created


async def test_create_report_persists_v1_with_ledger_event(session_factory: Factory) -> None:
    # Arrange / Act
    tenant_id, created = await _new_report(session_factory)

    # Assert
    loaded = await _get(session_factory, tenant_id, created.version.id)
    assert loaded == created
    assert loaded.version.number == 1
    assert loaded.is_current
    assert loaded.status.researcher.state is ReviewState.AWAITING_REVIEW
    async with tenant_session(session_factory, tenant_id) as session:
        event = await EvidenceService(session).get(tenant_id, loaded.evidence_event_id)
    assert event.kind is EventKind.ACTIVITY_RECORD
    assert event.payload["content_hash"] == loaded.content_hash


async def test_create_report_is_idempotent_and_refuses_different_content(
    session_factory: Factory,
) -> None:
    # Arrange
    tenant_id, project_id = fresh_ids()
    async with tenant_session(session_factory, tenant_id) as session:
        draft, first = await seed_report(session, tenant_id, project_id)
    changed = draft.model_copy(update={"summary": draft.summary + " Texto alterado."})

    # Act
    async with tenant_session(session_factory, tenant_id) as session:
        again = await ReportService(session).create_report(
            tenant_id, draft, actor=MAKER, source=EventSource.AGENT, is_synthetic=True
        )

    # Assert
    assert again.version.id == first.version.id
    with pytest.raises(ReportAlreadyExistsError):
        async with tenant_session(session_factory, tenant_id) as session:
            await ReportService(session).create_report(
                tenant_id, changed, actor=MAKER, source=EventSource.AGENT
            )


async def test_correction_creates_v2_and_preserves_v1(session_factory: Factory) -> None:
    # Arrange
    tenant_id, v1 = await _new_report(session_factory)

    # Act
    result = await _review(session_factory, tenant_id, v1.version.id, _correction(v1))

    # Assert
    new_version = result.new_version
    assert new_version is not None
    assert new_version.number == 2
    assert new_version.supersedes_id == v1.version.id
    old = await _get(session_factory, tenant_id, v1.version.id)
    assert old.version == v1.version
    assert not old.is_current
    assert old.current_version_id == new_version.id
    v2 = await _get(session_factory, tenant_id, new_version.id)
    async with tenant_session(session_factory, tenant_id) as session:
        event = await EvidenceService(session).get(tenant_id, v2.evidence_event_id)
    assert event.supersedes == v1.evidence_event_id
    assert event.source is EventSource.USER


async def test_review_of_old_version_conflicts_and_records_nothing(
    session_factory: Factory,
) -> None:
    # Arrange
    tenant_id, v1 = await _new_report(session_factory)
    await _review(session_factory, tenant_id, v1.version.id, _correction(v1))
    reviews_before = await _count_reviews(session_factory, tenant_id)

    # Act / Assert
    with pytest.raises(VersionConflictError) as raised:
        await _review(session_factory, tenant_id, v1.version.id, APPROVE)
    current = await _get(session_factory, tenant_id, v1.version.id)
    assert raised.value.current_id == current.current_version_id
    assert await _count_reviews(session_factory, tenant_id) == reviews_before
    v2 = await _get(session_factory, tenant_id, current.current_version_id)
    assert v2.status.researcher.state is ReviewState.AWAITING_REVIEW


async def test_old_approval_does_not_count_for_new_version(session_factory: Factory) -> None:
    # Arrange
    tenant_id, v1 = await _new_report(session_factory)
    await _review(session_factory, tenant_id, v1.version.id, APPROVE)

    # Act
    result = await _review(session_factory, tenant_id, v1.version.id, _correction(v1))

    # Assert
    assert result.new_version is not None
    v2 = await _get(session_factory, tenant_id, result.new_version.id)
    assert v2.status.researcher.state is ReviewState.AWAITING_REVIEW
    assert v2.status.approved_version_number == 1
    assert v2.status.approval_outdated


async def test_researcher_and_manager_reviews_are_independent(session_factory: Factory) -> None:
    # Arrange
    tenant_id, v1 = await _new_report(session_factory)

    # Act
    await _review(session_factory, tenant_id, v1.version.id, APPROVE)
    await _review(
        session_factory,
        tenant_id,
        v1.version.id,
        APPROVE,
        reviewer_id=MANAGER,
        reviewer_role=ReviewerRole.MANAGER,
    )

    # Assert
    status = (await _get(session_factory, tenant_id, v1.version.id)).status
    assert status.researcher.state is ReviewState.TEXT_APPROVED
    assert status.manager.state is ReviewState.TEXT_APPROVED
    assert not status.approval_outdated


async def test_only_the_author_reviews_as_researcher(session_factory: Factory) -> None:
    tenant_id, v1 = await _new_report(session_factory)

    with pytest.raises(ReviewerNotAllowedError):
        await _review(session_factory, tenant_id, v1.version.id, APPROVE, reviewer_id=uuid4())
    assert await _count_reviews(session_factory, tenant_id) == 0


async def test_correction_without_material_change_is_rejected(session_factory: Factory) -> None:
    # Arrange: reescreve o claim com o mesmo conteúdo
    tenant_id, v1 = await _new_report(session_factory)
    claim = v1.version.draft.claims[0]
    same = ReviseClaim(
        claim_id=v1.version.claim_ids[0],
        text=claim.text,
        status=claim.status,
        evidence_ids=claim.evidence_ids,
    )
    body = ReviewIn(
        decision=ReviewDecision.CHANGES_REQUESTED,
        correction=CorrectionIn(reason="Sem mudança de verdade.", operations=(same,)),
    )

    # Act / Assert
    with pytest.raises(ReportValidationError, match="alteração material"):
        await _review(session_factory, tenant_id, v1.version.id, body)
    assert (await _get(session_factory, tenant_id, v1.version.id)).is_current


async def test_citation_outside_tenant_project_is_rejected(session_factory: Factory) -> None:
    # Arrange: evidências gravadas em OUTRO projeto do mesmo tenant
    tenant_id, project_id = fresh_ids()
    async with tenant_session(session_factory, tenant_id) as session:
        foreign = await seed_draft(session, tenant_id, uuid4())
    draft = foreign.model_copy(update={"project_id": project_id})

    # Act / Assert
    with pytest.raises(ReportValidationError, match="não existem"):
        async with tenant_session(session_factory, tenant_id) as session:
            await ReportService(session).create_report(
                tenant_id, draft, actor=MAKER, source=EventSource.AGENT
            )


async def test_formal_hours_must_reference_formal_hours_event(session_factory: Factory) -> None:
    # Arrange
    tenant_id, project_id = fresh_ids()
    async with tenant_session(session_factory, tenant_id) as session:
        draft = await seed_draft(session, tenant_id, project_id)
        ledger = EvidenceService(session)
        commit = await ledger.append(make_event(tenant_id=tenant_id, project_id=project_id))
        hours = await ledger.append(
            make_event(
                tenant_id=tenant_id,
                project_id=project_id,
                kind=EventKind.FORMAL_HOURS_DECLARED,
                source=EventSource.USER,
                actor=Actor(type=ActorType.USER, id=str(RESEARCHER)),
                payload={"synthetic": True},
            )
        )
    with_commit = draft.model_copy(update={"formal_hours_event_ids": (commit.id,)})
    with_hours = draft.model_copy(update={"formal_hours_event_ids": (hours.id,)})

    # Act / Assert
    with pytest.raises(ReportValidationError, match="formal_hours_declared"):
        async with tenant_session(session_factory, tenant_id) as session:
            await ReportService(session).create_report(
                tenant_id, with_commit, actor=MAKER, source=EventSource.AGENT
            )
    async with tenant_session(session_factory, tenant_id) as session:
        created = await ReportService(session).create_report(
            tenant_id, with_hours, actor=MAKER, source=EventSource.AGENT
        )
    assert created.version.draft.formal_hours_event_ids == (hours.id,)


async def test_other_tenant_cannot_see_report(session_factory: Factory) -> None:
    # Arrange (session_factory = login de basho_api, sujeito à RLS)
    tenant_id, v1 = await _new_report(session_factory)
    other_tenant = uuid4()

    # Act / Assert: o serviço filtra por tenant...
    with pytest.raises(ReportNotFoundError):
        await _get(session_factory, other_tenant, v1.version.id)
    # ...e a RLS esconde as linhas de outro tenant e sem tenant definido, mesmo sem WHERE
    for table in REPORT_TABLES:
        async with tenant_session(session_factory, other_tenant) as session:
            rows = await session.execute(text(f"SELECT count(*) FROM {table}"))  # noqa: S608
            assert rows.scalar_one() == 0
    async with tenant_session(session_factory, tenant_id) as session:
        own = await session.execute(text("SELECT count(*) FROM report_versions"))
        assert own.scalar_one() == 1
    async with session_factory() as session, session.begin():
        no_tenant = await session.execute(text("SELECT count(*) FROM report_versions"))
        assert no_tenant.scalar_one() == 0


async def test_rls_rejects_insert_for_another_tenant(session_factory: Factory) -> None:
    tenant_id, other_tenant = uuid4(), uuid4()
    insert = (
        "INSERT INTO reporting_periods (id, tenant_id, start_date, end_date, timezone, "
        "periodicity) VALUES (gen_random_uuid(), :t, '2026-10-01', '2026-10-31', "
        "'America/Sao_Paulo', 'monthly')"
    )

    with pytest.raises(DBAPIError, match="row-level security"):
        async with tenant_session(session_factory, tenant_id) as session:
            await session.execute(text(insert), {"t": other_tenant})


async def test_worker_creates_versions_but_cannot_insert_review(
    worker_session_factory: Factory,
) -> None:
    # Arrange: o worker (processo do agente) grava a v1
    tenant_id, project_id = fresh_ids()
    async with tenant_session(worker_session_factory, tenant_id) as session:
        _, v1 = await seed_report(session, tenant_id, project_id)

    # Act / Assert: revisão é ação formal, só pelo endpoint humano (ADR-0005)
    with pytest.raises(DBAPIError, match="permission denied"):
        async with tenant_session(worker_session_factory, tenant_id) as session:
            await ReportService(session).review(
                tenant_id,
                v1.version.id,
                APPROVE,
                reviewer_id=MANAGER,
                reviewer_role=ReviewerRole.MANAGER,
            )


@pytest.mark.parametrize("table", REPORT_TABLES)
@pytest.mark.parametrize(
    "statement", ["UPDATE {t} SET tenant_id = tenant_id", "DELETE FROM {t}", "TRUNCATE {t}"]
)
async def test_app_role_has_no_update_delete_or_truncate(
    session_factory: Factory, table: str, statement: str
) -> None:
    tenant_id, _ = await _new_report(session_factory)

    with pytest.raises(DBAPIError, match="permission denied"):
        async with tenant_session(session_factory, tenant_id) as session:
            await session.execute(text(statement.format(t=table)))


@pytest.mark.parametrize("table", REPORT_TABLES)
@pytest.mark.parametrize("statement", ["UPDATE {t} SET tenant_id = tenant_id", "DELETE FROM {t}"])
async def test_update_and_delete_are_rejected_by_trigger_even_for_owner(
    session_factory: Factory, owner_session_factory: Factory, table: str, statement: str
) -> None:
    # Arrange: uma revisão garante linha nas três tabelas
    tenant_id, v1 = await _new_report(session_factory)
    await _review(session_factory, tenant_id, v1.version.id, APPROVE)

    # Act / Assert
    with pytest.raises(DBAPIError, match="append-only"):
        async with tenant_session(owner_session_factory, tenant_id) as session:
            await session.execute(text(statement.format(t=table)))


@pytest.mark.parametrize("table", REPORT_TABLES)
async def test_truncate_is_rejected_by_trigger_even_for_owner(
    owner_session_factory: Factory, table: str
) -> None:
    async with owner_session_factory() as session, session.begin():
        with pytest.raises(DBAPIError, match="append-only"):
            await session.execute(text(f"TRUNCATE {table} CASCADE"))
