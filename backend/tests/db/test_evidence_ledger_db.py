"""Integração do Evidence Ledger com Postgres real (trigger, FK, isolamento, paginação)."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from basho.db import tenant_session
from basho.evidence import (
    MAX_PAGE_SIZE,
    EvidenceNotFoundError,
    EvidenceService,
    EvidenceValidationError,
)
from basho.evidence.contracts import Actor, ActorType, EventKind, EventSource
from basho.evidence.domain.hashing import HASH_VERSION, compute_content_hash
from basho.evidence.repository import EvidenceRepository
from evidence_factories import fresh_ids, make_event

pytestmark = pytest.mark.db

Factory = async_sessionmaker[AsyncSession]
APPEND_ONLY = "append-only"


async def test_append_persists_event_with_hash_recomputable_from_stored_row(
    session_factory: Factory,
) -> None:
    # Arrange
    tenant_id, project_id = fresh_ids()
    new_event = make_event(tenant_id=tenant_id, project_id=project_id)

    # Act
    async with tenant_session(session_factory, tenant_id) as session:
        saved = await EvidenceService(session).append(new_event)
    async with tenant_session(session_factory, tenant_id) as session:
        loaded = await EvidenceService(session).get(tenant_id, saved.id)

    # Assert
    assert loaded == saved
    assert loaded.content_hash == compute_content_hash(new_event)
    assert compute_content_hash(loaded) == loaded.content_hash
    assert loaded.created_at.tzinfo is not None
    assert loaded.payload == new_event.payload


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE evidence_events SET source_ref = 'x' WHERE tenant_id = :t",
        "DELETE FROM evidence_events WHERE tenant_id = :t",
    ],
)
async def test_update_and_delete_are_rejected_by_trigger(
    session_factory: Factory, statement: str
) -> None:
    # Arrange
    tenant_id, project_id = fresh_ids()
    async with tenant_session(session_factory, tenant_id) as session:
        await EvidenceService(session).append(
            make_event(tenant_id=tenant_id, project_id=project_id)
        )

    # Act / Assert
    with pytest.raises(DBAPIError, match=APPEND_ONLY):
        async with tenant_session(session_factory, tenant_id) as session:
            await session.execute(text(statement), {"t": tenant_id})


async def test_truncate_is_rejected_by_trigger(session_factory: Factory) -> None:
    async with session_factory() as session, session.begin():
        with pytest.raises(DBAPIError, match=APPEND_ONLY):
            # CASCADE: sem ele a FK de report_versions (#39) barra antes do trigger
            await session.execute(text("TRUNCATE evidence_events CASCADE"))


async def test_correction_appends_new_event_and_leaves_original_untouched(
    session_factory: Factory,
) -> None:
    # Arrange
    tenant_id, project_id = fresh_ids()
    async with tenant_session(session_factory, tenant_id) as session:
        service = EvidenceService(session)
        original = await service.append(make_event(tenant_id=tenant_id, project_id=project_id))

        # Act
        correction = await service.append(
            make_event(
                tenant_id=tenant_id,
                project_id=project_id,
                kind=EventKind.USER_CORRECTION,
                source=EventSource.USER,
                actor=Actor(type=ActorType.USER, id="u1"),
                supersedes=original.id,
                payload={"corrected": True},
            )
        )

    # Assert
    async with tenant_session(session_factory, tenant_id) as session:
        reloaded = await EvidenceService(session).get(tenant_id, original.id)
    assert correction.supersedes == original.id
    assert correction.id != original.id
    assert reloaded == original


async def test_supersedes_event_of_other_tenant_is_rejected_by_service(
    session_factory: Factory,
) -> None:
    # Arrange
    tenant_a, project_a = fresh_ids()
    tenant_b, project_b = fresh_ids()
    async with tenant_session(session_factory, tenant_a) as session:
        foreign = await EvidenceService(session).append(
            make_event(tenant_id=tenant_a, project_id=project_a)
        )

    # Act / Assert
    async with tenant_session(session_factory, tenant_b) as session:
        with pytest.raises(EvidenceValidationError, match="não encontrado"):
            await EvidenceService(session).append(
                make_event(tenant_id=tenant_b, project_id=project_b, supersedes=foreign.id)
            )


async def test_supersedes_event_of_other_project_is_rejected_by_service(
    session_factory: Factory,
) -> None:
    tenant_id, project_id = fresh_ids()
    async with tenant_session(session_factory, tenant_id) as session:
        service = EvidenceService(session)
        original = await service.append(make_event(tenant_id=tenant_id, project_id=project_id))

        with pytest.raises(EvidenceValidationError, match="outro projeto"):
            await service.append(
                make_event(tenant_id=tenant_id, project_id=uuid4(), supersedes=original.id)
            )


async def test_cross_tenant_supersedes_is_rejected_by_database_foreign_key(
    session_factory: Factory,
) -> None:
    # Arrange
    tenant_a, project_a = fresh_ids()
    tenant_b, project_b = fresh_ids()
    async with tenant_session(session_factory, tenant_a) as session:
        foreign = await EvidenceService(session).append(
            make_event(tenant_id=tenant_a, project_id=project_a)
        )

    # Act / Assert: SQL cru, contornando o serviço
    insert_sql = text(
        "INSERT INTO evidence_events (id, tenant_id, project_id, kind, source, actor, payload, "
        "content_hash, hash_version, supersedes) VALUES (:id, :t, :p, 'commit_observed', "
        "'github', '{}'::jsonb, '{}'::jsonb, :h, 1, :s)"
    )
    with pytest.raises(IntegrityError, match="fk_evidence_events_supersedes_same_project"):
        async with tenant_session(session_factory, tenant_b) as session:
            await session.execute(
                insert_sql,
                {"id": uuid4(), "t": tenant_b, "p": project_b, "h": "0" * 64, "s": foreign.id},
            )


async def test_get_and_query_do_not_see_events_of_other_tenant(session_factory: Factory) -> None:
    # Arrange
    tenant_a, project_a = fresh_ids()
    tenant_b, _ = fresh_ids()
    async with tenant_session(session_factory, tenant_a) as session:
        saved = await EvidenceService(session).append(
            make_event(tenant_id=tenant_a, project_id=project_a)
        )

    # Act / Assert
    async with tenant_session(session_factory, tenant_b) as session:
        service = EvidenceService(session)
        with pytest.raises(EvidenceNotFoundError):
            await service.get(tenant_b, saved.id)
        assert await service.query(tenant_b, project_id=project_a) == []
        assert await service.query(tenant_b) == []


async def test_query_paginates_newest_first_without_gaps_or_repeats(
    session_factory: Factory,
) -> None:
    # Arrange: um commit por evento, para created_at distintos
    tenant_id, project_id = fresh_ids()
    saved_ids: set[UUID] = set()
    for index in range(5):
        async with tenant_session(session_factory, tenant_id) as session:
            event = await EvidenceService(session).append(
                make_event(tenant_id=tenant_id, project_id=project_id, payload={"n": index})
            )
            saved_ids.add(event.id)

    # Act
    collected: list[UUID] = []
    async with tenant_session(session_factory, tenant_id) as session:
        service = EvidenceService(session)
        cursor = None
        while page := await service.query(tenant_id, project_id=project_id, limit=2, before=cursor):
            collected.extend(event.id for event in page)
            cursor = (page[-1].created_at, page[-1].id)

    # Assert
    assert len(collected) == len(set(collected)) == 5
    assert set(collected) == saved_ids


async def test_query_orders_by_created_at_desc_and_filters_by_kind_and_project(
    session_factory: Factory,
) -> None:
    tenant_id, project_id = fresh_ids()
    kinds = [EventKind.COMMIT_OBSERVED, EventKind.ISSUE_OBSERVED, EventKind.COMMIT_OBSERVED]
    for kind in kinds:
        async with tenant_session(session_factory, tenant_id) as session:
            await EvidenceService(session).append(
                make_event(tenant_id=tenant_id, project_id=project_id, kind=kind)
            )
    async with tenant_session(session_factory, tenant_id) as session:
        await EvidenceService(session).append(make_event(tenant_id=tenant_id, project_id=uuid4()))

    async with tenant_session(session_factory, tenant_id) as session:
        service = EvidenceService(session)
        everything = await service.query(tenant_id, project_id=project_id)
        commits = await service.query(
            tenant_id, project_id=project_id, kinds=[EventKind.COMMIT_OBSERVED]
        )

    assert [e.created_at for e in everything] == sorted(
        (e.created_at for e in everything), reverse=True
    )
    assert len(everything) == 3
    assert len(commits) == 2
    assert {e.kind for e in commits} == {EventKind.COMMIT_OBSERVED}


async def test_query_limit_is_capped_at_maximum_page_size(session_factory: Factory) -> None:
    tenant_id, project_id = fresh_ids()
    async with tenant_session(session_factory, tenant_id) as session:
        service = EvidenceService(session)
        await service.append(make_event(tenant_id=tenant_id, project_id=project_id))

        page = await service.query(tenant_id, limit=MAX_PAGE_SIZE * 1000)

    assert len(page) == 1


async def test_tenant_session_sets_tenant_setting_for_the_transaction(
    session_factory: Factory,
) -> None:
    tenant_id = uuid4()
    async with tenant_session(session_factory, tenant_id) as session:
        value = (
            await session.execute(text("SELECT current_setting('app.tenant_id')"))
        ).scalar_one()

    assert value == str(tenant_id)


async def test_session_of_tenant_a_cannot_use_service_for_tenant_b(
    session_factory: Factory,
) -> None:
    # Arrange
    tenant_a, project_a = fresh_ids()
    tenant_b, project_b = fresh_ids()
    async with tenant_session(session_factory, tenant_b) as session:
        foreign = await EvidenceService(session).append(
            make_event(tenant_id=tenant_b, project_id=project_b)
        )

    # Act / Assert
    async with tenant_session(session_factory, tenant_a) as session:
        service = EvidenceService(session)
        with pytest.raises(EvidenceValidationError, match="tenant da sessão"):
            await service.get(tenant_b, foreign.id)
        with pytest.raises(EvidenceValidationError, match="tenant da sessão"):
            await service.query(tenant_b)
        with pytest.raises(EvidenceValidationError, match="tenant da sessão"):
            await service.append(make_event(tenant_id=tenant_b, project_id=project_b))
    assert project_a != project_b


async def test_session_without_tenant_setting_is_rejected(session_factory: Factory) -> None:
    tenant_id, project_id = fresh_ids()
    async with session_factory() as session, session.begin():
        service = EvidenceService(session)
        with pytest.raises(EvidenceValidationError, match="tenant da sessão"):
            await service.append(make_event(tenant_id=tenant_id, project_id=project_id))


async def test_append_stores_hash_version(session_factory: Factory) -> None:
    tenant_id, project_id = fresh_ids()
    async with tenant_session(session_factory, tenant_id) as session:
        saved = await EvidenceService(session).append(
            make_event(tenant_id=tenant_id, project_id=project_id)
        )
        version = (
            await session.execute(
                text("SELECT hash_version FROM evidence_events WHERE id = :i"), {"i": saved.id}
            )
        ).scalar_one()

    assert version == HASH_VERSION


async def test_supersedes_across_projects_of_same_tenant_is_rejected_by_database_foreign_key(
    session_factory: Factory,
) -> None:
    # Arrange
    tenant_id, project_a = fresh_ids()
    project_b = uuid4()
    async with tenant_session(session_factory, tenant_id) as session:
        original = await EvidenceService(session).append(
            make_event(tenant_id=tenant_id, project_id=project_a)
        )

    # Act / Assert: SQL cru, contornando o serviço
    insert_sql = text(
        "INSERT INTO evidence_events (id, tenant_id, project_id, kind, source, actor, payload, "
        "content_hash, hash_version, supersedes) VALUES (:id, :t, :p, 'commit_observed', "
        "'github', '{}'::jsonb, '{}'::jsonb, :h, 1, :s)"
    )
    with pytest.raises(IntegrityError, match="fk_evidence_events_supersedes_same_project"):
        async with tenant_session(session_factory, tenant_id) as session:
            await session.execute(
                insert_sql,
                {"id": uuid4(), "t": tenant_id, "p": project_b, "h": "0" * 64, "s": original.id},
            )


async def test_query_with_empty_kinds_returns_nothing(session_factory: Factory) -> None:
    tenant_id, project_id = fresh_ids()
    async with tenant_session(session_factory, tenant_id) as session:
        service = EvidenceService(session)
        await service.append(make_event(tenant_id=tenant_id, project_id=project_id))

        assert await service.query(tenant_id, kinds=[]) == []
        assert len(await service.query(tenant_id, kinds=None)) == 1


async def test_nul_character_is_rejected_before_reaching_database(
    session_factory: Factory,
) -> None:
    tenant_id, project_id = fresh_ids()
    async with tenant_session(session_factory, tenant_id) as session:
        with pytest.raises(EvidenceValidationError, match=r"U\+0000"):
            await EvidenceService(session).append(
                make_event(tenant_id=tenant_id, project_id=project_id, payload={"k": "a\x00b"})
            )


async def test_integrity_error_on_insert_becomes_generic_validation_error(
    session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange: simula violação de restrição no insert (ex.: corrida)
    async def failing_insert(*args: object, **kwargs: object) -> None:
        raise IntegrityError("INSERT secret-detail", {}, Exception("secret-detail"))

    monkeypatch.setattr(EvidenceRepository, "insert", failing_insert)
    tenant_id, project_id = fresh_ids()

    # Act / Assert
    async with tenant_session(session_factory, tenant_id) as session:
        with pytest.raises(EvidenceValidationError) as raised:
            await EvidenceService(session).append(
                make_event(tenant_id=tenant_id, project_id=project_id)
            )
    assert "secret-detail" not in str(raised.value)


async def test_missing_ids_returns_only_ids_absent_from_tenant_and_project(
    session_factory: Factory,
) -> None:
    # Arrange
    tenant_id, project_id = fresh_ids()
    other_tenant, other_project = fresh_ids()
    async with tenant_session(session_factory, tenant_id) as session:
        service = EvidenceService(session)
        mine = await service.append(make_event(tenant_id=tenant_id, project_id=project_id))
        elsewhere = await service.append(make_event(tenant_id=tenant_id, project_id=other_project))
    async with tenant_session(session_factory, other_tenant) as session:
        foreign = await EvidenceService(session).append(
            make_event(tenant_id=other_tenant, project_id=project_id)
        )
    unknown = uuid4()

    # Act
    async with tenant_session(session_factory, tenant_id) as session:
        missing = await EvidenceService(session).missing_ids(
            tenant_id, project_id, [mine.id, elsewhere.id, foreign.id, unknown, unknown]
        )

    # Assert
    assert missing == {elsewhere.id, foreign.id, unknown}
