"""Serviço público de projetos, pendências, aprovação formal e dossiê (#5).

A transação é do chamador (``tenant_session``). Estado é derivado do ledger e das tabelas
append-only da 0005; nada é atualizado no lugar (ADR-0003).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from basho.compliance.api_contracts import (
    ActivityOut,
    ApprovalDecision,
    ApprovalIn,
    ApprovalOut,
    DossierEntryOut,
    DossierOut,
    PendingAnswerIn,
    PendingAnswerOut,
    PendingItemOut,
    PendingKind,
    PendingPageOut,
    PendingStatus,
    ProjectOut,
)
from basho.evidence import EvidenceService
from basho.evidence.contracts import (
    Actor,
    ActorType,
    ArtifactStatus,
    EventKind,
    EventSource,
    EvidenceEvent,
    NewEvidenceEvent,
)
from basho.evidence.domain.rules import EvidenceNotFoundError
from basho.evidence.propagation import CorrectionPropagation
from basho.identity import HumanIdentity, HumanRole
from basho.projects.ledger_view import VIEW_KINDS, ArtifactView, build_artifacts, decision_of
from basho.projects.models import (
    ActivityRow,
    ArtifactApprovalRow,
    PendingAnswerRow,
    PendingItemRow,
    ProjectRow,
)
from basho.projects.repository import ProjectRepository

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200
LEDGER_PAGE_SIZE = 200
MAX_VIEW_EVENTS = 5000
APPROVABLE = frozenset({ArtifactStatus.VERIFIED})
REJECTABLE = frozenset({ArtifactStatus.VERIFIED, ArtifactStatus.NEEDS_HUMAN})
CLOSED_ARTIFACT = frozenset({ArtifactStatus.APPROVED, ArtifactStatus.REJECTED})


class ProjectError(Exception):
    """Base dos erros do módulo. Mensagens sem dados do payload."""


class ProjectNotFoundError(ProjectError):
    """Projeto, pendência ou artefato inexistente no tenant."""


class ProjectForbiddenError(ProjectError):
    """Papel humano sem permissão para a ação."""


class ProjectConflictError(ProjectError):
    """A ação não vale no estado atual (409)."""

    def __init__(self, code: str, current_status: str | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.current_status = current_status


class ProjectViewTooLargeError(ProjectError):
    """Ledger do projeto passou do limite de leitura do MVP."""


@dataclass(frozen=True)
class _ProjectState:
    project: ProjectRow
    artifacts: dict[UUID, ArtifactView]
    pending: list[PendingItemRow]
    answers: dict[UUID, PendingAnswerRow]
    approvals: dict[UUID, ArtifactApprovalRow]

    def artifact_status(self, artifact_id: UUID) -> ArtifactStatus | None:
        view = self.artifacts.get(artifact_id)
        if view is None:
            return None
        approval = self.approvals.get(artifact_id)
        decisions = {} if approval is None else {artifact_id: approval.decision}
        return view.status(decision_of(decisions, artifact_id))

    def pending_status(self, row: PendingItemRow) -> PendingStatus:
        if row.id in self.answers:
            return PendingStatus.ANSWERED
        status = self.artifact_status(row.artifact_event_id)
        view = self.artifacts.get(row.artifact_event_id)
        latest = None if view is None else view.latest_verification
        stale = latest is None or latest.id != row.verification_event_id
        approval_lapsed = row.kind == PendingKind.APPROVAL_REQUIRED and status is not (
            ArtifactStatus.VERIFIED
        )
        if stale or status in CLOSED_ARTIFACT or approval_lapsed:
            return PendingStatus.RESOLVED
        return PendingStatus.OPEN

    def pending_out(self, row: PendingItemRow) -> PendingItemOut:
        status = self.pending_status(row)
        answer = self.answers.get(row.id)
        return PendingItemOut(
            id=row.id,
            project_id=row.project_id,
            activity_id=row.activity_id,
            kind=PendingKind(row.kind),
            title=row.title,
            question=row.question,
            assignee_role=row.assignee_role,
            artifact_id=row.artifact_event_id,
            artifact_status=self.artifact_status(row.artifact_event_id),
            verification_event_id=row.verification_event_id,
            status=status,
            resolved=status is not PendingStatus.OPEN,
            response=None if answer is None else answer.answer,
            created_at=row.created_at,
        )

    def open_pending(self) -> list[PendingItemRow]:
        return [row for row in self.pending if self.pending_status(row) is PendingStatus.OPEN]


def _approval_out(row: ArtifactApprovalRow) -> ApprovalOut:
    decision = ApprovalDecision(row.decision)
    status = (
        ArtifactStatus.APPROVED if decision is ApprovalDecision.APPROVE else ArtifactStatus.REJECTED
    )
    return ApprovalOut(
        artifact_id=row.artifact_event_id,
        decision=decision,
        status=status,
        approver_id=row.approver_id,
        comment=row.comment,
        evidence_event_id=row.evidence_event_id,
        created_at=row.created_at,
    )


def _human_actor(human: HumanIdentity) -> Actor:
    return Actor(type=ActorType.USER, id=str(human.user_id))


class ProjectService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repository = ProjectRepository(session)
        self._evidence = EvidenceService(session)

    # --- cadastro (seed #14 e testes; sem endpoint no MVP) ---

    async def create_project(
        self,
        tenant_id: UUID,
        name: str,
        *,
        description: str | None = None,
        is_synthetic: bool = False,
    ) -> UUID:
        row = await self._repository.insert(
            ProjectRow,
            {
                "id": uuid4(),
                "tenant_id": tenant_id,
                "name": name,
                "description": description,
                "is_synthetic": is_synthetic,
            },
        )
        return row.id

    async def create_activity(
        self,
        tenant_id: UUID,
        project_id: UUID,
        title: str,
        *,
        description: str | None = None,
        is_synthetic: bool = False,
    ) -> UUID:
        row = await self._repository.insert(
            ActivityRow,
            {
                "id": uuid4(),
                "tenant_id": tenant_id,
                "project_id": project_id,
                "title": title,
                "description": description,
                "is_synthetic": is_synthetic,
            },
        )
        return row.id

    # --- leitura ---

    async def get_project(self, tenant_id: UUID, project_id: UUID) -> ProjectOut:
        state = await self._state(tenant_id, project_id)
        return await self._project_out(state)

    async def list_pending(
        self,
        tenant_id: UUID,
        project_id: UUID,
        *,
        status: PendingStatus | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
        offset: int = 0,
    ) -> PendingPageOut:
        state = await self._state(tenant_id, project_id)
        items = [state.pending_out(row) for row in state.pending]
        if status is not None:
            items = [item for item in items if item.status is status]
        bounded = max(1, min(limit, MAX_PAGE_SIZE))
        start = max(0, offset)
        page = items[start : start + bounded]
        has_more = start + bounded < len(items)
        return PendingPageOut(items=tuple(page), next_offset=start + bounded if has_more else None)

    async def dossier(self, tenant_id: UUID, project_id: UUID) -> DossierOut:
        state = await self._state(tenant_id, project_id)
        entries = [await self._dossier_entry(state, view) for view in state.artifacts.values()]
        return DossierOut(project=await self._project_out(state), entries=tuple(entries))

    # --- ações humanas ---

    async def answer(
        self, tenant_id: UUID, pending_id: UUID, body: PendingAnswerIn, human: HumanIdentity
    ) -> PendingAnswerOut:
        row = await self._repository.get_pending(tenant_id, pending_id)
        if row is None:
            raise ProjectNotFoundError("pendência não encontrada")
        # Mesmo lock da decisão formal: resposta e aprovação do artefato não correm juntas.
        await self._repository.lock(f"artifact:{tenant_id}:{row.artifact_event_id}")
        state = await self._state(tenant_id, row.project_id)
        if row.kind == PendingKind.APPROVAL_REQUIRED:
            raise ProjectConflictError("approval_via_artifact_endpoint")
        if human.role.value != row.assignee_role:
            raise ProjectForbiddenError("só o papel designado responde à pendência")
        status = state.pending_status(row)
        if status is not PendingStatus.OPEN:
            raise ProjectConflictError("pending_closed", status.value)
        event = await self._evidence.append(
            NewEvidenceEvent(
                tenant_id=tenant_id,
                project_id=row.project_id,
                kind=EventKind.USER_CORRECTION,
                source=EventSource.USER,
                source_ref=f"pending:{row.id}",
                actor=_human_actor(human),
                payload={
                    "pending_item_id": str(row.id),
                    "pending_kind": row.kind,
                    "source_key": row.source_key,
                    "answer": body.answer,
                    "corrected_payload": body.corrected_payload,
                    "answered_role": human.role.value,
                    "identity_verified": False,  # placeholder de identidade até #47
                },
                supersedes=row.artifact_event_id,  # o artefato original não muda
                is_synthetic=row.is_synthetic,
            )
        )
        # Mesma transação: o que cita o artefato corrigido vai para needs_review (#11).
        await CorrectionPropagation(self._session).propagate(tenant_id, event.id)
        await self._repository.insert(
            PendingAnswerRow,
            {
                "id": uuid4(),
                "tenant_id": tenant_id,
                "pending_item_id": row.id,
                "answer": body.answer,
                "corrected_payload": body.corrected_payload,
                "answered_by": human.user_id,
                "answered_role": human.role.value,
                "correction_event_id": event.id,
            },
        )
        refreshed = await self._state(tenant_id, row.project_id)
        return PendingAnswerOut(pending=refreshed.pending_out(row), correction_event_id=event.id)

    async def decide(
        self, tenant_id: UUID, artifact_id: UUID, body: ApprovalIn, human: HumanIdentity
    ) -> ApprovalOut:
        """Aprovação/rejeição FORMAL do artefato. Só humano com papel `manager` (ADR-0005)."""
        if human.role is not HumanRole.MANAGER:
            raise ProjectForbiddenError("só o gestor decide formalmente")
        await self._repository.lock(f"artifact:{tenant_id}:{artifact_id}")
        try:
            artifact = await self._evidence.get(tenant_id, artifact_id)
        except EvidenceNotFoundError:
            raise ProjectNotFoundError("artefato não encontrado") from None
        state = await self._state(tenant_id, artifact.project_id)
        status = state.artifact_status(artifact_id)
        if status is None:
            raise ProjectNotFoundError("artefato não encontrado")
        self._check_decidable(state, artifact_id, status, body.decision)
        event = await self._evidence.append(self._decision_event(artifact, status, body, human))
        try:
            row = await self._repository.insert(
                ArtifactApprovalRow,
                {
                    "id": uuid4(),
                    "tenant_id": tenant_id,
                    "project_id": artifact.project_id,
                    "artifact_event_id": artifact_id,
                    "decision": body.decision.value,
                    "comment": body.comment,
                    "approver_id": human.user_id,
                    "evidence_event_id": event.id,
                },
            )
        except IntegrityError:
            raise ProjectConflictError("already_decided") from None
        return _approval_out(row)

    # --- internos ---

    @staticmethod
    def _check_decidable(
        state: _ProjectState, artifact_id: UUID, status: ArtifactStatus, decision: ApprovalDecision
    ) -> None:
        if artifact_id in state.approvals:
            raise ProjectConflictError("already_decided", status.value)
        if decision is ApprovalDecision.REJECT:
            if status not in REJECTABLE:
                raise ProjectConflictError("artifact_not_rejectable", status.value)
            return
        if status not in APPROVABLE:
            raise ProjectConflictError("artifact_not_verified", status.value)
        blocking = [
            row
            for row in state.open_pending()
            if row.artifact_event_id == artifact_id and row.kind != PendingKind.APPROVAL_REQUIRED
        ]
        if blocking:
            raise ProjectConflictError("open_pending", status.value)

    @staticmethod
    def _decision_event(
        artifact: EvidenceEvent, status: ArtifactStatus, body: ApprovalIn, human: HumanIdentity
    ) -> NewEvidenceEvent:
        approve = body.decision is ApprovalDecision.APPROVE
        target = ArtifactStatus.APPROVED if approve else ArtifactStatus.REJECTED
        return NewEvidenceEvent(
            tenant_id=artifact.tenant_id,
            project_id=artifact.project_id,
            kind=EventKind.USER_CONFIRMATION if approve else EventKind.STATUS_CHANGED,
            source=EventSource.USER,
            source_ref=f"artifact:{artifact.id}",
            actor=_human_actor(human),
            payload={
                "artifact_event_id": str(artifact.id),
                "decision": body.decision.value,
                "from_status": status.value,
                "to_status": target.value,
                "status": target.value,  # mesma chave dos status_changed da propagação (#11)
                "comment": body.comment,
                "decided_role": human.role.value,
                "identity_verified": False,  # placeholder de identidade até #47
            },
            is_synthetic=artifact.is_synthetic,
        )

    async def _state(self, tenant_id: UUID, project_id: UUID) -> _ProjectState:
        """Carrega o projeto, materializa as pendências dos vereditos e lê respostas/decisões."""
        if await self._repository.current_tenant_setting() != str(tenant_id):
            raise ProjectError("tenant da sessão ausente ou diferente do informado")
        project = await self._repository.get_project(tenant_id, project_id)
        if project is None:
            raise ProjectNotFoundError("projeto não encontrado")
        artifacts = build_artifacts(await self._project_events(tenant_id, project_id))
        await self._repository.insert_pending_if_absent(
            self._pending_rows(tenant_id, project_id, artifacts)
        )
        return _ProjectState(
            project=project,
            artifacts=artifacts,
            pending=await self._repository.pending_of(tenant_id, project_id),
            answers={
                row.pending_item_id: row
                for row in await self._repository.answers_of(tenant_id, project_id)
            },
            approvals={
                row.artifact_event_id: row
                for row in await self._repository.approvals_of(tenant_id, project_id)
            },
        )

    async def _project_events(self, tenant_id: UUID, project_id: UUID) -> list[EvidenceEvent]:
        events: list[EvidenceEvent] = []
        before: tuple[datetime, UUID] | None = None
        while True:
            page = await self._evidence.query(
                tenant_id,
                project_id=project_id,
                kinds=VIEW_KINDS,
                limit=LEDGER_PAGE_SIZE,
                before=before,
            )
            events.extend(page)
            if len(events) > MAX_VIEW_EVENTS:
                raise ProjectViewTooLargeError("ledger do projeto acima do limite do MVP")
            if len(page) < LEDGER_PAGE_SIZE:
                return events
            before = (page[-1].created_at, page[-1].id)

    @staticmethod
    def _pending_rows(
        tenant_id: UUID, project_id: UUID, artifacts: dict[UUID, ArtifactView]
    ) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for view in artifacts.values():
            latest = view.latest_verification
            if latest is None:
                continue
            for spec in view.pending_specs():
                rows.append(
                    {
                        "id": uuid4(),
                        "tenant_id": tenant_id,
                        "project_id": project_id,
                        "activity_id": spec.activity_id,
                        "kind": spec.kind.value,
                        "source_key": spec.source_key,
                        "title": spec.title,
                        "question": spec.question,
                        "assignee_role": spec.assignee_role.value,
                        "artifact_event_id": view.event.id,
                        "verification_event_id": latest.id,
                        "is_synthetic": view.event.is_synthetic,
                    }
                )
        return rows

    async def _project_out(self, state: _ProjectState) -> ProjectOut:
        project = state.project
        activities = await self._repository.activities_of(project.tenant_id, project.id)
        return ProjectOut(
            id=project.id,
            name=project.name,
            description=project.description,
            is_synthetic=project.is_synthetic,
            created_at=project.created_at,
            activities=tuple(
                ActivityOut(
                    id=row.id,
                    project_id=row.project_id,
                    title=row.title,
                    description=row.description,
                    is_synthetic=row.is_synthetic,
                    created_at=row.created_at,
                )
                for row in activities
            ),
            open_pending=len(state.open_pending()),
        )

    async def _dossier_entry(self, state: _ProjectState, view: ArtifactView) -> DossierEntryOut:
        event = view.event
        status = state.artifact_status(event.id)
        sources: Sequence[EvidenceEvent] = await self._evidence.get_many(
            event.tenant_id, event.project_id, view.cited_evidence_ids()
        )
        approval = state.approvals.get(event.id)
        return DossierEntryOut(
            artifact_id=event.id,
            activity_id=view.activity_id,
            title=view.title,
            status=status or ArtifactStatus.PROPOSED,
            content=view.draft,
            evidence=tuple(sources),
            verifications=tuple(view.verification_results()),
            history=tuple(view.history()),
            approval=None if approval is None else _approval_out(approval),
            run_id=view.run_id,
            runs=(),  # métricas do AgentRun chegam com agent_runs (0006, #10)
        )
