"""Propagação de correções (#11) com Postgres real, como os roles da aplicação.

Parametrizado por ``basho_api`` e ``basho_worker``: os dois podem propagar (o #5 chama pela
API e o #10 pelo worker), sempre só com SELECT/INSERT.
"""

import json
from collections.abc import Sequence
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from basho.db import tenant_session
from basho.evidence import (
    CorrectionPropagation,
    EvidenceNotFoundError,
    EvidenceService,
    EvidenceValidationError,
    PropagationResult,
)
from basho.evidence.contracts import (
    Actor,
    ActorType,
    ArtifactStatus,
    EventKind,
    EventSource,
    NewEvidenceEvent,
)
from evidence_factories import fresh_ids, make_event
from report_factories import report

pytestmark = pytest.mark.db

Factory = async_sessionmaker[AsyncSession]
MAKER = Actor(type=ActorType.AGENT, id="maker", model="test-maker-model")
REVIEWER = Actor(type=ActorType.USER, id="reviewer-1")
STATUS_COUNT_SQL = (
    "SELECT count(*) FROM evidence_events WHERE kind = 'status_changed' "
    "AND payload ->> 'artifact_event_id' = :artifact"
)


@pytest.fixture(params=["api", "worker"])
def app_factory(
    request: pytest.FixtureRequest, session_factory: Factory, worker_session_factory: Factory
) -> Factory:
    return session_factory if request.param == "api" else worker_session_factory


class Ledger:
    """Monta cenários num tenant/projeto isolados."""

    def __init__(self, factory: Factory) -> None:
        self.factory = factory
        self.tenant_id, self.project_id = fresh_ids()

    async def evidence(self) -> UUID:
        return await self._append(make_event(tenant_id=self.tenant_id, project_id=self.project_id))

    async def formal_hours(self) -> UUID:
        return await self._append(
            make_event(
                tenant_id=self.tenant_id,
                project_id=self.project_id,
                kind=EventKind.FORMAL_HOURS_DECLARED,
                source=EventSource.USER,
                actor=REVIEWER,
                payload={"hours_ref": "timesheet-1"},
            )
        )

    async def artifact(
        self,
        cites: Sequence[UUID] = (),
        *,
        formal_hours: Sequence[UUID] = (),
        supersedes: UUID | None = None,
    ) -> UUID:
        draft = {
            "summary": "rascunho sintético",
            "claims": [{"text": "afirmação", "evidence_ids": [str(i) for i in cites]}],
            "formal_hours_event_ids": [str(i) for i in formal_hours],
            "missing": [],
        }
        return await self._append(
            make_event(
                tenant_id=self.tenant_id,
                project_id=self.project_id,
                kind=EventKind.ACTIVITY_RECORD,
                source=EventSource.AGENT,
                actor=MAKER,
                payload={"draft": draft},
                supersedes=supersedes,
            )
        )

    async def approve(self, artifact_id: UUID) -> UUID:
        return await self._append(
            make_event(
                tenant_id=self.tenant_id,
                project_id=self.project_id,
                kind=EventKind.USER_CONFIRMATION,
                source=EventSource.USER,
                actor=REVIEWER,
                source_ref=f"artifact:{artifact_id}",
                payload={"decision": "approved"},
            )
        )

    async def correct(self, superseded_id: UUID) -> UUID:
        return await self._append(
            make_event(
                tenant_id=self.tenant_id,
                project_id=self.project_id,
                kind=EventKind.USER_CORRECTION,
                source=EventSource.USER,
                actor=REVIEWER,
                payload={"corrected": True},
                supersedes=superseded_id,
            )
        )

    async def propagate(self, correction_id: UUID) -> PropagationResult:
        async with tenant_session(self.factory, self.tenant_id) as session:
            return await CorrectionPropagation(session).propagate(self.tenant_id, correction_id)

    async def pending(self) -> list[UUID]:
        async with tenant_session(self.factory, self.tenant_id) as session:
            reviews = await CorrectionPropagation(session).pending_reviews(
                self.tenant_id, self.project_id
            )
        return [review.artifact_event_id for review in reviews]

    async def status_count(self, artifact_id: UUID) -> int:
        async with tenant_session(self.factory, self.tenant_id) as session:
            result = await session.execute(text(STATUS_COUNT_SQL), {"artifact": str(artifact_id)})
        return int(result.scalar_one())

    async def _append(self, event: NewEvidenceEvent) -> UUID:
        async with tenant_session(self.factory, self.tenant_id) as session:
            return (await EvidenceService(session).append(event)).id


@pytest.fixture
def ledger(app_factory: Factory) -> Ledger:
    return Ledger(app_factory)


async def test_correcting_evidence_of_approved_record_moves_it_to_needs_review(
    ledger: Ledger,
) -> None:
    # Arrange
    evidence = await ledger.evidence()
    record = await ledger.artifact([evidence])
    await ledger.approve(record)
    correction = await ledger.correct(evidence)

    # Act
    result = await ledger.propagate(correction)

    # Assert
    assert [mark.artifact_event_id for mark in result.marked] == [record]
    assert await ledger.pending() == [record]


async def test_status_event_records_cause_and_is_appended_by_system(ledger: Ledger) -> None:
    # Arrange
    evidence = await ledger.evidence()
    record = await ledger.artifact([evidence])
    correction = await ledger.correct(evidence)

    # Act
    result = await ledger.propagate(correction)

    # Assert
    async with tenant_session(ledger.factory, ledger.tenant_id) as session:
        status = await EvidenceService(session).get(
            ledger.tenant_id, result.marked[0].status_event_id
        )
        original = await EvidenceService(session).get(ledger.tenant_id, record)
    assert status.kind is EventKind.STATUS_CHANGED
    assert status.actor.type is ActorType.SYSTEM
    assert status.source is EventSource.SYSTEM
    assert status.payload["status"] == ArtifactStatus.NEEDS_REVIEW.value
    assert status.payload["artifact_event_id"] == str(record)
    assert status.payload["cause_event_id"] == str(correction)
    assert status.payload["superseded_event_id"] == str(evidence)
    assert status.payload["via_event_id"] == str(evidence)
    assert original.payload["draft"]["claims"][0]["evidence_ids"] == [str(evidence)]


async def test_transitive_dependents_are_also_marked(ledger: Ledger) -> None:
    # Arrange: report cita o registro, que cita a evidência
    evidence = await ledger.evidence()
    record = await ledger.artifact([evidence])
    report = await ledger.artifact([record])
    correction = await ledger.correct(evidence)

    # Act
    result = await ledger.propagate(correction)

    # Assert
    by_artifact = {mark.artifact_event_id: mark for mark in result.marked}
    assert set(by_artifact) == {record, report}
    assert by_artifact[report].via_event_id == record
    assert by_artifact[report].depth == 2
    assert set(await ledger.pending()) == {record, report}


async def test_reprocessing_the_same_correction_does_not_duplicate_transitions(
    ledger: Ledger,
) -> None:
    # Arrange
    evidence = await ledger.evidence()
    record = await ledger.artifact([evidence])
    correction = await ledger.correct(evidence)
    await ledger.propagate(correction)

    # Act
    again = await ledger.propagate(correction)

    # Assert
    assert again.marked == ()
    assert again.already_marked == (record,)
    assert await ledger.status_count(record) == 1


async def test_non_dependent_artifacts_stay_untouched(ledger: Ledger) -> None:
    # Arrange
    corrected = await ledger.evidence()
    unrelated = await ledger.evidence()
    dependent = await ledger.artifact([corrected])
    independent = await ledger.artifact([unrelated])
    correction = await ledger.correct(corrected)

    # Act
    result = await ledger.propagate(correction)

    # Assert
    assert [mark.artifact_event_id for mark in result.marked] == [dependent]
    assert await ledger.status_count(independent) == 0


async def test_citation_cycle_terminates_and_marks_each_artifact_once(ledger: Ledger) -> None:
    # Arrange: a cita a evidência; b cita a; c cita b e a (diamante + volta)
    evidence = await ledger.evidence()
    first = await ledger.artifact([evidence])
    second = await ledger.artifact([first])
    third = await ledger.artifact([second, first])
    correction = await ledger.correct(evidence)

    # Act
    result = await ledger.propagate(correction)

    # Assert
    marked = [mark.artifact_event_id for mark in result.marked]
    assert sorted(marked, key=str) == sorted([first, second, third], key=str)
    for artifact in (first, second, third):
        assert await ledger.status_count(artifact) == 1


async def test_superseded_artifact_version_is_not_marked(ledger: Ledger) -> None:
    # Arrange: v2 substitui v1; as duas citam a evidência
    evidence = await ledger.evidence()
    old_version = await ledger.artifact([evidence])
    new_version = await ledger.artifact([evidence], supersedes=old_version)
    correction = await ledger.correct(evidence)

    # Act
    result = await ledger.propagate(correction)

    # Assert
    assert [mark.artifact_event_id for mark in result.marked] == [new_version]
    assert await ledger.status_count(old_version) == 0


async def test_correcting_formal_hours_marks_artifacts_that_reference_them(
    ledger: Ledger,
) -> None:
    # Arrange
    hours = await ledger.formal_hours()
    record = await ledger.artifact(formal_hours=[hours])
    correction = await ledger.correct(hours)

    # Act
    result = await ledger.propagate(correction)

    # Assert
    assert [mark.artifact_event_id for mark in result.marked] == [record]


async def test_reopen_as_draft_clears_pending_and_records_previous_status(
    ledger: Ledger,
) -> None:
    # Arrange
    evidence = await ledger.evidence()
    record = await ledger.artifact([evidence])
    result = await ledger.propagate(await ledger.correct(evidence))

    # Act
    async with tenant_session(ledger.factory, ledger.tenant_id) as session:
        reopened = await CorrectionPropagation(session).reopen_as_draft(ledger.tenant_id, record)

    # Assert
    assert reopened.payload["status"] == ArtifactStatus.DRAFT.value
    assert reopened.payload["previous_status_event_id"] == str(result.marked[0].status_event_id)
    assert await ledger.pending() == []


async def test_reopen_requires_needs_review(ledger: Ledger) -> None:
    # Arrange
    evidence = await ledger.evidence()
    record = await ledger.artifact([evidence])

    # Act / Assert
    with pytest.raises(EvidenceValidationError, match="needs_review"):
        async with tenant_session(ledger.factory, ledger.tenant_id) as session:
            await CorrectionPropagation(session).reopen_as_draft(ledger.tenant_id, record)


async def test_new_correction_after_reopen_marks_again_with_new_cause(ledger: Ledger) -> None:
    # Arrange: corrigida, reaberta pelo worker e corrigida de novo por outra correção
    evidence = await ledger.evidence()
    record = await ledger.artifact([evidence])
    await ledger.propagate(await ledger.correct(evidence))
    async with tenant_session(ledger.factory, ledger.tenant_id) as session:
        await CorrectionPropagation(session).reopen_as_draft(ledger.tenant_id, record)
    second_correction = await ledger.correct(evidence)

    # Act
    result = await ledger.propagate(second_correction)

    # Assert
    assert [mark.artifact_event_id for mark in result.marked] == [record]
    assert await ledger.pending() == [record]
    assert await ledger.status_count(record) == 3


async def test_propagating_an_event_without_supersedes_is_rejected(ledger: Ledger) -> None:
    # Arrange
    evidence = await ledger.evidence()

    # Act / Assert
    with pytest.raises(EvidenceValidationError, match="supersedes"):
        await ledger.propagate(evidence)


async def test_correction_of_another_tenant_is_not_visible(ledger: Ledger) -> None:
    # Arrange: correção existe em outro tenant
    other = Ledger(ledger.factory)
    evidence = await other.evidence()
    await other.artifact([evidence])
    foreign_correction = await other.correct(evidence)

    # Act / Assert: a RLS esconde o evento; nada é marcado em nenhum tenant
    with pytest.raises(EvidenceNotFoundError):
        await ledger.propagate(foreign_correction)
    assert await other.pending() == []


async def test_pending_reviews_require_session_of_same_tenant(ledger: Ledger) -> None:
    # Act / Assert
    with pytest.raises(EvidenceValidationError, match="tenant da sessão"):
        async with tenant_session(ledger.factory, uuid4()) as session:
            await CorrectionPropagation(session).pending_reviews(
                ledger.tenant_id, ledger.project_id
            )


async def test_real_research_report_draft_shape_is_matched(ledger: Ledger) -> None:
    # Arrange: rascunho real (ResearchReportDraft) serializado como o Maker grava (#8)
    method = await ledger.evidence()
    result_evidence = await ledger.evidence()
    hours = await ledger.formal_hours()
    draft = report(
        method_ids=(method,), result_ids=(result_evidence,), formal_hours_event_ids=(hours,)
    ).model_copy(update={"project_id": ledger.project_id})
    async with tenant_session(ledger.factory, ledger.tenant_id) as session:
        record = (
            await EvidenceService(session).append(
                make_event(
                    tenant_id=ledger.tenant_id,
                    project_id=ledger.project_id,
                    kind=EventKind.ACTIVITY_RECORD,
                    source=EventSource.AGENT,
                    actor=MAKER,
                    payload={"draft": json.loads(draft.model_dump_json())},
                )
            )
        ).id

    # Act: corrige cada evidência citada (claim, experimento, horas formais)
    results = [
        await ledger.propagate(await ledger.correct(cited))
        for cited in (method, result_evidence, hours)
    ]

    # Assert
    for result in results:
        assert [mark.artifact_event_id for mark in result.marked] == [record]
    assert await ledger.status_count(record) == 3
