"""Adaptador relatório → análise fiscal: os 6 critérios de aceite da proposta do Codex."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from basho.compliance.report_evidence import (
    FORMAL_HOURS_KIND,
    TEXT_ONLY_NOTE,
    Gap,
    ItemStatus,
    ResolvedEvidence,
    ScopeMismatchError,
    build_report_evidence,
)
from basho.expenses.domain.models import Scope
from basho.reports import (
    ReportCorrection,
    ReportInput,
    ReportVersion,
    ReviewDecision,
    ReviewerRole,
    apply_correction,
    review_version,
)
from basho.reports.corrections import ReviseClaim
from reports_helpers import MANAGER, RESEARCHER_ANA, TENANT, at, first_version

PROJECT = UUID("11111111-1111-4111-8111-111111111111")
E42 = UUID("aaaaaaaa-0000-4000-8000-000000000042")
E43 = UUID("aaaaaaaa-0000-4000-8000-000000000043")
C94 = UUID("bbbbbbbb-0000-4000-8000-0000000c94ab")
HOURS = UUID("dddddddd-0000-4000-8000-000000000201")
SCOPE = Scope(tenant_id=TENANT, project_id=PROJECT, fiscal_year=2026)


class FakeResolver:
    def __init__(self, events: dict[UUID, ResolvedEvidence]) -> None:
        self.events = events

    def resolve(self, evidence_id: UUID) -> ResolvedEvidence | None:
        return self.events.get(evidence_id)


def _event(eid: UUID, kind: str = "PR_MERGED", **overrides: object) -> ResolvedEvidence:
    data: dict[str, object] = {
        "id": eid,
        "tenant_id": TENANT,
        "project_id": PROJECT,
        "kind": kind,
        "source_ref": f"ref-{str(eid)[:4]}",
        "content_hash": f"sha256:{eid.hex}",
        "origin": "github",
    }
    data.update(overrides)
    return ResolvedEvidence.model_validate(data)


def _resolver(**overrides: ResolvedEvidence | None) -> FakeResolver:
    events = {E42: _event(E42), E43: _event(E43), C94: _event(C94, "COMMIT")}
    for key, value in overrides.items():
        eid = {"e42": E42, "e43": E43, "c94": C94, "hours": HOURS}[key]
        if value is None:
            events.pop(eid, None)
        else:
            events[eid] = value
    return FakeResolver(events)


def _approve(history: list[ReportVersion], version: ReportVersion) -> ReportInput:
    review = review_version(
        history,
        review_id=uuid4(),
        version_id=version.id,
        reviewer_id=RESEARCHER_ANA,
        reviewer_role=ReviewerRole.RESEARCHER,
        decision=ReviewDecision.TEXT_APPROVED,
        reviewed_at=at(1),
    )
    return ReportInput(versions=tuple(history), reviews=(review,))


# Critério 1 — escopo e localizador
def test_rejects_reports_outside_authorized_scope() -> None:
    other = Scope(tenant_id=uuid4(), project_id=PROJECT, fiscal_year=2026)
    with pytest.raises(ScopeMismatchError):
        build_report_evidence(other, [ReportInput(versions=(first_version(),))], _resolver())


def test_every_item_has_exact_locator_and_resolved_sources() -> None:
    v1 = first_version()
    dossier = build_report_evidence(SCOPE, [ReportInput(versions=(v1,))], _resolver())
    item_ids = {*v1.claim_ids, *v1.experiment_ids, *v1.missing_ids}
    assert {i.item_id for i in dossier.items} == item_ids
    for item in dossier.items:
        for src in item.sources:
            assert src.locator == f"report:{v1.id}/{item.item_kind.value}/{item.item_id}"
            assert src.revision.startswith("sha256:")
            assert (src.tenant_id, src.project_id) == (TENANT, PROJECT)


# Critério 2 — revisão aplicada e autoridade
def test_manager_only_review_is_not_researcher_confirmation() -> None:
    v1 = first_version()
    manager = review_version(
        [v1],
        review_id=uuid4(),
        version_id=v1.id,
        reviewer_id=MANAGER,
        reviewer_role=ReviewerRole.MANAGER,
        decision=ReviewDecision.TEXT_APPROVED,
        reviewed_at=at(1),
    )
    dossier = build_report_evidence(
        SCOPE, [ReportInput(versions=(v1,), reviews=(manager,))], _resolver()
    )
    (r,) = dossier.researchers
    assert r.researcher_review_id is None
    assert Gap.RESEARCHER_TEXT_REVIEW_MISSING in r.gaps
    assert all(i.researcher_review_id is None for i in dossier.items)


def test_researcher_approval_is_carried_by_exact_review_id_and_never_confirms_fiscal() -> None:
    v1 = first_version()
    report = _approve([v1], v1)
    dossier = build_report_evidence(SCOPE, [report], _resolver())
    (r,) = dossier.researchers
    assert r.researcher_review_id == report.reviews[0].id
    assert Gap.RESEARCHER_TEXT_REVIEW_MISSING not in r.gaps
    assert dossier.note == TEXT_ONLY_NOTE
    assert not hasattr(dossier, "confirmed")


# Critério 3 — v2 não herda aprovação da v1
def test_correction_after_approval_reopens_review() -> None:
    v1 = first_version()
    approved = _approve([v1], v1)
    correction = ReportCorrection(
        base_version_id=v1.id,
        author_id=RESEARCHER_ANA,
        author_role="pesquisador",
        reason="Hipótese registrada no PR #43.",
        operations=(
            ReviseClaim(
                claim_id=v1.claim_ids[3],
                text="Hipótese: SMOTE recupera a classe rara de vibração.",
                status="supported",
                evidence_ids=(E43,),
            ),
        ),
    )
    v2 = apply_correction([v1], correction, new_version_id=uuid4(), created_at=at(2))
    dossier = build_report_evidence(
        SCOPE, [ReportInput(versions=(v1, v2), reviews=approved.reviews)], _resolver()
    )
    (r,) = dossier.researchers
    assert r.version_number == 2
    assert {Gap.RESEARCHER_TEXT_REVIEW_MISSING, Gap.RESEARCHER_APPROVAL_OUTDATED} <= set(r.gaps)
    assert all(i.version_id == v2.id for i in dossier.items)


# Critério 4 — negativos, conflitos, lacunas e evidência ausente/fora/substituída
def test_negative_result_is_preserved_even_without_resolvable_evidence() -> None:
    dossier = build_report_evidence(
        SCOPE, [ReportInput(versions=(first_version(),))], _resolver(c94=None)
    )
    negative = next(i for i in dossier.items if i.status is ItemStatus.RESULT_NEGATIVE)
    assert Gap.EVIDENCE_UNRESOLVED in negative.gaps
    assert negative.sources == ()


def test_supported_claim_without_valid_evidence_becomes_pending() -> None:
    foreign = _event(E42, project_id=uuid4())
    dossier = build_report_evidence(
        SCOPE, [ReportInput(versions=(first_version(),))], _resolver(e42=foreign)
    )
    challenge = next(i for i in dossier.items if "latência de inferência sem perda" in i.text)
    assert challenge.status is ItemStatus.PENDING
    assert Gap.EVIDENCE_OUT_OF_SCOPE in challenge.gaps


def test_superseded_evidence_is_a_gap_not_support() -> None:
    replaced = _event(E42, superseded_by=uuid4())
    dossier = build_report_evidence(
        SCOPE, [ReportInput(versions=(first_version(),))], _resolver(e42=replaced)
    )
    assert any(Gap.EVIDENCE_SUPERSEDED in i.gaps for i in dossier.items)
    assert all(s.reference != f"evidence:{E42}" for i in dossier.items for s in i.sources)


def test_pending_claim_keeps_partial_evidence_and_question() -> None:
    dossier = build_report_evidence(SCOPE, [ReportInput(versions=(first_version(),))], _resolver())
    pending = next(i for i in dossier.items if i.status is ItemStatus.PENDING)
    assert Gap.OPEN_QUESTION in pending.gaps
    assert [s.reference for s in pending.sources] == [f"evidence:{E43}"]
    assert "SMOTE" in pending.text


# Critério 5 — horas só por evento formal
def test_hours_missing_and_non_formal_hours_are_gaps() -> None:
    missing = build_report_evidence(SCOPE, [ReportInput(versions=(first_version(),))], _resolver())
    assert Gap.FORMAL_HOURS_MISSING in missing.researchers[0].gaps
    v1 = first_version()
    wrong = v1.model_copy(
        update={"draft": v1.draft.model_copy(update={"formal_hours_event_ids": (E42,)})}
    )
    dossier = build_report_evidence(SCOPE, [ReportInput(versions=(wrong,))], _resolver())
    assert Gap.FORMAL_HOURS_NOT_FORMAL in dossier.researchers[0].gaps
    assert dossier.researchers[0].formal_hours == ()


def test_formal_hours_event_is_referenced_never_summed() -> None:
    v1 = first_version()
    with_hours = v1.model_copy(
        update={"draft": v1.draft.model_copy(update={"formal_hours_event_ids": (HOURS,)})}
    )
    resolver = _resolver(hours=_event(HOURS, FORMAL_HOURS_KIND, origin="formal_system"))
    dossier = build_report_evidence(SCOPE, [ReportInput(versions=(with_hours,))], resolver)
    (r,) = dossier.researchers
    assert [s.reference for s in r.formal_hours] == [f"evidence:{HOURS}"]
    assert r.formal_hours[0].origin == "formal_system"
    assert Gap.FORMAL_HOURS_MISSING not in r.gaps


# Critério 6 — período operacional vs. ano-base
def test_period_is_related_to_fiscal_year_without_replacing_it() -> None:
    report = [ReportInput(versions=(first_version(),))]
    same = build_report_evidence(SCOPE, report, _resolver())
    other = build_report_evidence(
        Scope(tenant_id=TENANT, project_id=PROJECT, fiscal_year=2025), report, _resolver()
    )
    assert same.period_gaps == ()
    assert other.period_gaps == (Gap.PERIOD_OUTSIDE_FISCAL_YEAR,)
    assert other.scope.fiscal_year == 2025
    assert (other.period_start.year, other.period_end.year) == (2026, 2026)
