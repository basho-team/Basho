"""Persistência de versões e revisões de relatório (#39) sobre o domínio do PR #43.

As regras (versão atual, papel do revisor, correção → N+1) são do domínio puro
(`review_version`, `apply_correction`); este serviço só carrega o histórico, chama o domínio
e grava o resultado. Cada versão e cada revisão também vira evento do ledger, na MESMA
transação, que pertence ao chamador (``tenant_session``). A série (tenant, projeto,
pesquisador, período) é serializada por advisory lock.

TODO(#11): alteração material (nova versão) deve devolver dependentes a ``needs_review``;
ainda não há projeção de dependentes, então nada é propagado aqui.
"""

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from basho.agent.artifacts import ReportingPeriod, ResearchReportDraft
from basho.agent.checks import ReportDeterministicChecker
from basho.agent.verifier import VerificationResult
from basho.evidence import EvidenceNotFoundError, EvidenceService
from basho.evidence.contracts import Actor, ActorType, EventKind, EventSource, NewEvidenceEvent
from basho.reports.consolidation import ReportInput, consolidate
from basho.reports.corrections import ReportCorrection, apply_correction
from basho.reports.models import ReportReviewRow, ReportVersionRow
from basho.reports.repository import ReportRepository
from basho.reports.schemas import ReportVersionOut, ReviewIn, ReviewOut
from basho.reports.versions import (
    ChangeRecord,
    ReportReview,
    ReportVersion,
    ReviewDecision,
    ReviewerRole,
    create_first_version,
    review_version,
)

REPORT_ARTIFACT = "research_report"


class ReportPersistenceError(Exception):
    """Base dos erros de persistência de reports. Mensagens sem conteúdo do relatório."""


class ReportNotFoundError(ReportPersistenceError):
    """Versão inexistente no tenant."""


class ReportValidationError(ReportPersistenceError):
    """Entrada viola uma regra de persistência (citação, tenant, alteração material)."""


class ReportAlreadyExistsError(ReportPersistenceError):
    """A série já tem versão com outro conteúdo: alteração entra como correção."""

    def __init__(self, current_version_id: UUID) -> None:
        super().__init__("relatório já existe para este período; envie uma correção")
        self.current_version_id = current_version_id


def content_hash(draft: ResearchReportDraft) -> str:
    """SHA-256 do JSON canônico do draft (chaves ordenadas, UTF-8)."""
    canonical = json.dumps(
        draft.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def cited_evidence_ids(version: ReportVersion) -> tuple[UUID, ...]:
    """Evidências citadas pelo draft e pelas lacunas resolvidas, sem repetição."""
    draft = version.draft
    cited: set[UUID] = set(draft.formal_hours_event_ids)
    for claim in draft.claims:
        cited.update(claim.evidence_ids)
    for experiment in draft.experiments:
        cited.update(experiment.evidence_ids)
    if version.change is not None:
        for gap in version.change.resolved_gaps:
            cited.update(gap.evidence_ids, gap.formal_hours_event_ids)
    return tuple(sorted(cited, key=str))


def _series_key(tenant_id: UUID, project_id: UUID, researcher_id: UUID, period_id: UUID) -> str:
    return f"report:{tenant_id}:{project_id}:{researcher_id}:{period_id}"


def _to_version(row: ReportVersionRow) -> ReportVersion:
    return ReportVersion(
        id=row.id,
        tenant_id=row.tenant_id,
        number=row.number,
        draft=ResearchReportDraft.model_validate(row.draft),
        claim_ids=tuple(row.claim_ids),
        experiment_ids=tuple(row.experiment_ids),
        missing_ids=tuple(row.missing_ids),
        supersedes_id=row.supersedes_id,
        change=None if row.change is None else ChangeRecord.model_validate(row.change),
        created_at=row.created_at,
        is_synthetic=row.is_synthetic,
    )


def _to_review(row: ReportReviewRow) -> ReportReview:
    return ReportReview(
        id=row.id,
        version_id=row.report_version_id,
        reviewer_id=row.reviewer_id,
        reviewer_role=ReviewerRole(row.reviewer_role),
        decision=ReviewDecision(row.decision),
        comment=row.comment,
        reviewed_at=row.reviewed_at,
    )


def _user_actor(user_id: UUID) -> Actor:
    return Actor(type=ActorType.USER, id=str(user_id))


class ReportService:
    def __init__(self, session: AsyncSession) -> None:
        self._repository = ReportRepository(session)
        self._ledger = EvidenceService(session)

    async def _require_session_tenant(self, tenant_id: UUID) -> None:
        if await self._repository.current_tenant_setting() != str(tenant_id):
            raise ReportValidationError("tenant da sessão ausente ou diferente do informado")

    async def _require_row(self, tenant_id: UUID, version_id: UUID) -> ReportVersionRow:
        row = await self._repository.get_version(tenant_id, version_id)
        if row is None:
            raise ReportNotFoundError("versão de relatório não encontrada neste tenant")
        return row

    async def _series_of(self, row: ReportVersionRow) -> list[ReportVersionRow]:
        return await self._repository.series(
            row.tenant_id, row.project_id, row.researcher_id, row.reporting_period_id
        )

    # --- leitura -------------------------------------------------------------------------

    async def get_version(self, tenant_id: UUID, version_id: UUID) -> ReportVersionOut:
        await self._require_session_tenant(tenant_id)
        row = await self._require_row(tenant_id, version_id)
        return await self._to_out(row, await self._series_of(row))

    async def _to_out(
        self, row: ReportVersionRow, rows: list[ReportVersionRow]
    ) -> ReportVersionOut:
        history = tuple(_to_version(item) for item in rows)
        review_rows = await self._repository.reviews_of(row.tenant_id, [item.id for item in rows])
        reviews = tuple(_to_review(item) for item in review_rows)
        status = consolidate([ReportInput(versions=history, reviews=reviews)]).reports[0]
        current = rows[-1]
        return ReportVersionOut(
            version=_to_version(row),
            status=status,
            is_current=row.id == current.id,
            current_version_id=current.id,
            reporting_period_id=row.reporting_period_id,
            content_hash=row.content_hash,
            evidence_event_id=row.evidence_event_id,
        )

    # --- criação da v1 -------------------------------------------------------------------

    async def create_report(
        self,
        tenant_id: UUID,
        draft: ResearchReportDraft,
        *,
        actor: Actor,
        source: EventSource,
        is_synthetic: bool = False,
    ) -> ReportVersionOut:
        """Grava a v1 da série. Mesmo conteúdo da versão atual é idempotente."""
        await self._require_session_tenant(tenant_id)
        period_id = await self._repository.get_or_create_period(tenant_id, draft.period)
        await self._repository.lock_series(
            _series_key(tenant_id, draft.project_id, draft.researcher_id, period_id)
        )
        rows = await self._repository.series(
            tenant_id, draft.project_id, draft.researcher_id, period_id
        )
        if rows:
            if rows[-1].content_hash != content_hash(draft):
                raise ReportAlreadyExistsError(rows[-1].id)
            return await self._to_out(rows[-1], rows)
        version = create_first_version(
            version_id=uuid4(),
            tenant_id=tenant_id,
            draft=draft,
            created_at=datetime.now(UTC),
            is_synthetic=is_synthetic,
        )
        row = await self._persist_version(version, period_id, actor=actor, source=source)
        return await self._to_out(row, [row])

    async def _check_citations(self, version: ReportVersion) -> None:
        """Evidências existem no tenant/projeto; horas só de `FORMAL_HOURS_DECLARED`."""
        tenant_id, project_id = version.tenant_id, version.draft.project_id
        missing = await self._ledger.missing_ids(tenant_id, project_id, cited_evidence_ids(version))
        if missing:
            msg = f"{len(missing)} evidência(s) citada(s) não existem neste tenant e projeto"
            raise ReportValidationError(msg)
        for event_id in version.draft.formal_hours_event_ids:
            try:
                event = await self._ledger.get(tenant_id, event_id)
            except EvidenceNotFoundError:
                raise ReportValidationError("evento de horas não encontrado") from None
            if event.kind is not EventKind.FORMAL_HOURS_DECLARED:
                raise ReportValidationError("horas só por referência a formal_hours_declared")

    async def _persist_version(
        self,
        version: ReportVersion,
        period_id: UUID,
        *,
        actor: Actor,
        source: EventSource,
        previous_event_id: UUID | None = None,
    ) -> ReportVersionRow:
        await self._check_citations(version)
        digest = content_hash(version.draft)
        change = None if version.change is None else version.change.model_dump(mode="json")
        draft = version.draft.model_dump(mode="json")
        event = await self._ledger.append(
            NewEvidenceEvent(
                tenant_id=version.tenant_id,
                project_id=version.draft.project_id,
                kind=EventKind.ACTIVITY_RECORD,
                source=source,
                source_ref=str(version.id),
                actor=actor,
                payload={
                    "artifact": REPORT_ARTIFACT,
                    "report_version_id": str(version.id),
                    "number": version.number,
                    "reporting_period_id": str(period_id),
                    "content_hash": digest,
                    "draft": draft,
                    "change": change,
                    # Versão de correção humana: identidade afirmada pelo BFF (placeholder).
                    **({"identity_verified": False} if source is EventSource.USER else {}),
                },
                supersedes=previous_event_id,
                is_synthetic=version.is_synthetic,
            )
        )
        values = {
            "id": version.id,
            "tenant_id": version.tenant_id,
            "project_id": version.draft.project_id,
            "researcher_id": version.draft.researcher_id,
            "reporting_period_id": period_id,
            "number": version.number,
            "supersedes_id": version.supersedes_id,
            "draft": draft,
            "claim_ids": list(version.claim_ids),
            "experiment_ids": list(version.experiment_ids),
            "missing_ids": list(version.missing_ids),
            "change": change,
            "content_hash": digest,
            "evidence_event_id": event.id,
            "cited_evidence_ids": list(cited_evidence_ids(version)),
            "is_synthetic": version.is_synthetic,
            "created_at": version.created_at,
        }
        try:
            return await self._repository.insert_version(values)
        except IntegrityError:
            raise ReportValidationError("versão viola uma restrição de integridade") from None

    # --- revisão -------------------------------------------------------------------------

    async def review(
        self,
        tenant_id: UUID,
        version_id: UUID,
        body: ReviewIn,
        *,
        reviewer_id: UUID,
        reviewer_role: ReviewerRole,
    ) -> ReviewOut:
        """Revisão humana da versão exata (ação formal, ADR-0005).

        Propaga do domínio: `VersionConflictError` (versão não é a atual → 409),
        `ReviewerNotAllowedError` (403) e `InvalidCorrectionError` (422).
        """
        await self._require_session_tenant(tenant_id)
        row = await self._require_row(tenant_id, version_id)
        await self._repository.lock_series(
            _series_key(tenant_id, row.project_id, row.researcher_id, row.reporting_period_id)
        )
        history = tuple(_to_version(item) for item in await self._series_of(row))
        reviewed_at = datetime.now(UTC)
        review = review_version(
            history,
            review_id=uuid4(),
            version_id=version_id,
            reviewer_id=reviewer_id,
            reviewer_role=reviewer_role,
            decision=body.decision,
            reviewed_at=reviewed_at,
            comment=body.comment,
        )
        new_version = await self._apply_correction(row, history, body, review)
        event_id = await self._record_review(row, review, new_version)
        return ReviewOut(review=review, evidence_event_id=event_id, new_version=new_version)

    async def _apply_correction(
        self,
        row: ReportVersionRow,
        history: tuple[ReportVersion, ...],
        body: ReviewIn,
        review: ReportReview,
    ) -> ReportVersion | None:
        if body.correction is None:
            return None
        correction = ReportCorrection(
            base_version_id=row.id,
            author_id=review.reviewer_id,
            author_role=review.reviewer_role.value,
            reason=body.correction.reason,
            operations=body.correction.operations,
        )
        new_version = apply_correction(
            history, correction, new_version_id=uuid4(), created_at=review.reviewed_at
        )
        if content_hash(new_version.draft) == row.content_hash:
            raise ReportValidationError("correção sem alteração material no relatório")
        await self._persist_version(
            new_version,
            row.reporting_period_id,
            actor=_user_actor(review.reviewer_id),
            source=EventSource.USER,
            previous_event_id=row.evidence_event_id,
        )
        return new_version

    async def _record_review(
        self, row: ReportVersionRow, review: ReportReview, new_version: ReportVersion | None
    ) -> UUID:
        approved = review.decision is ReviewDecision.TEXT_APPROVED
        new_version_id = None if new_version is None else new_version.id
        event = await self._ledger.append(
            NewEvidenceEvent(
                tenant_id=row.tenant_id,
                project_id=row.project_id,
                kind=EventKind.USER_CONFIRMATION if approved else EventKind.USER_CORRECTION,
                source=EventSource.USER,
                source_ref=str(row.id),
                actor=_user_actor(review.reviewer_id),
                payload={
                    "artifact": REPORT_ARTIFACT,
                    "report_review_id": str(review.id),
                    "report_version_id": str(row.id),
                    "number": row.number,
                    "reviewer_role": review.reviewer_role.value,
                    "decision": review.decision.value,
                    "comment": review.comment,
                    "new_version_id": None if new_version_id is None else str(new_version_id),
                    # Identidade afirmada pelo BFF, não autenticada aqui (placeholder até a
                    # auth real): o registro formal deixa isso explícito.
                    "identity_verified": False,
                },
                supersedes=None if approved else row.evidence_event_id,
                is_synthetic=row.is_synthetic,
            )
        )
        values = {
            "id": review.id,
            "tenant_id": row.tenant_id,
            "report_version_id": row.id,
            "reviewer_id": review.reviewer_id,
            "reviewer_role": review.reviewer_role.value,
            "decision": review.decision.value,
            "comment": review.comment,
            "new_version_id": new_version_id,
            "evidence_event_id": event.id,
            "is_synthetic": row.is_synthetic,
            "reviewed_at": review.reviewed_at,
        }
        try:
            await self._repository.insert_review(values)
        except IntegrityError:
            raise ReportValidationError("revisão viola uma restrição de integridade") from None
        return event.id


# --- leitura para a jornada (lista, histórico, consolidação, checks) ----------------------


class ReportQueryService:
    """Leituras da jornada pesquisador → gerente → fiscal. Não grava nada."""

    def __init__(self, session: AsyncSession) -> None:
        self._repository = ReportRepository(session)
        self._ledger = EvidenceService(session)
        self._reports = ReportService(session)

    async def project_inputs(
        self, tenant_id: UUID, project_id: UUID, period: ReportingPeriod
    ) -> list[ReportInput]:
        """Histórico e revisões de cada série do projeto no período (vazio se não houver)."""
        await self._reports._require_session_tenant(tenant_id)
        period_id = await self._repository.find_period(tenant_id, period)
        if period_id is None:
            return []
        rows = await self._repository.project_versions(tenant_id, project_id, period_id)
        reviews = await self._repository.reviews_of(tenant_id, [row.id for row in rows])
        by_researcher: dict[UUID, list[ReportVersionRow]] = {}
        for row in rows:
            by_researcher.setdefault(row.researcher_id, []).append(row)
        inputs = []
        for series in by_researcher.values():
            ids = {row.id for row in series}
            inputs.append(
                ReportInput(
                    versions=tuple(_to_version(row) for row in series),
                    reviews=tuple(_to_review(r) for r in reviews if r.report_version_id in ids),
                )
            )
        return inputs

    async def list_current(
        self, tenant_id: UUID, project_id: UUID, period: ReportingPeriod
    ) -> list[ReportVersionOut]:
        await self._reports._require_session_tenant(tenant_id)
        period_id = await self._repository.find_period(tenant_id, period)
        if period_id is None:
            return []
        rows = await self._repository.project_versions(tenant_id, project_id, period_id)
        by_researcher: dict[UUID, list[ReportVersionRow]] = {}
        for row in rows:
            by_researcher.setdefault(row.researcher_id, []).append(row)
        return [
            await self._reports._to_out(series[-1], series) for series in by_researcher.values()
        ]

    async def history(self, tenant_id: UUID, version_id: UUID) -> list[ReportVersionOut]:
        await self._reports._require_session_tenant(tenant_id)
        row = await self._reports._require_row(tenant_id, version_id)
        series = await self._reports._series_of(row)
        return [await self._reports._to_out(item, series) for item in series]

    async def run_checks(self, tenant_id: UUID, version_id: UUID) -> VerificationResult:
        """Checks determinísticos (#9) sobre a versão, com as evidências citadas do ledger."""
        await self._reports._require_session_tenant(tenant_id)
        row = await self._reports._require_row(tenant_id, version_id)
        version = _to_version(row)
        evidence = []
        for event_id in cited_evidence_ids(version):
            try:
                evidence.append(await self._ledger.get(tenant_id, event_id))
            except EvidenceNotFoundError:
                continue  # o check acusa unknown_evidence
        return ReportDeterministicChecker(tenant_id).check(version.draft, evidence)
