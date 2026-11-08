"""Rotas de evidência (`/api/v1/projects/{id}/evidence`): registrar e consultar o ledger.

Registro humano (pesquisador): `source=user`. Append-only: corrigir = novo evento com
`supersedes`. Horas só como `formal_hours_declared` declaradas por humano.
"""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from basho.evidence import EvidenceService, EvidenceValidationError
from basho.evidence.contracts import (
    Actor,
    ActorType,
    EventKind,
    EventSource,
    EvidenceEvent,
    NewEvidenceEvent,
)
from basho.reports.api import Reviewer, _scope, current_reviewer
from basho.reports.versions import ReviewerRole

router = APIRouter(tags=["evidence"])

HUMAN_KINDS = frozenset(
    {
        EventKind.ACTIVITY_RECORD,
        EventKind.TECHNICAL_JUSTIFICATION,
        EventKind.FORMAL_HOURS_DECLARED,
        EventKind.USER_CORRECTION,
    }
)


class EvidenceIn(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    kind: EventKind
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=10, max_length=4000)
    source_ref: str | None = Field(default=None, max_length=200)
    hours: float | None = Field(default=None, gt=0, le=744, description="Só formal_hours")
    supersedes: UUID | None = None
    researcher_id: UUID | None = Field(
        default=None,
        description="A quem o registro se refere (ex.: horas declaradas pela coordenação)",
    )


@router.post(
    "/projects/{project_id}/evidence",
    response_model=EvidenceEvent,
    status_code=status.HTTP_201_CREATED,
)
async def register_evidence(
    project_id: UUID,
    body: EvidenceIn,
    request: Request,
    reviewer: Annotated[Reviewer, Depends(current_reviewer)],
) -> EvidenceEvent:
    if body.kind not in HUMAN_KINDS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "tipo não registrável por humano"
        )
    is_hours = body.kind is EventKind.FORMAL_HOURS_DECLARED
    if is_hours and reviewer.role is not ReviewerRole.MANAGER:
        # Regra 6: horas formais vêm de registro confirmado por quem tem autoridade
        # (coordenação/RH), nunca autodeclaradas pelo pesquisador.
        msg = "horas formais só podem ser declaradas pela coordenação"
        raise HTTPException(status.HTTP_403_FORBIDDEN, msg)
    if is_hours != (body.hours is not None):
        msg = "horas só (e obrigatoriamente) em formal_hours_declared"
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, msg)
    payload: dict[str, Any] = {"title": body.title, "description": body.description}
    if body.researcher_id is not None:
        payload["researcher_id"] = str(body.researcher_id)
    if is_hours:
        payload["hours"] = body.hours
        payload["declared_by_role"] = reviewer.role.value
    settings = request.app.state.settings
    event = NewEvidenceEvent(
        tenant_id=settings.tenant_id,
        project_id=project_id,
        kind=body.kind,
        source=EventSource.USER,
        source_ref=body.source_ref,
        actor=Actor(type=ActorType.USER, id=str(reviewer.user_id)),
        payload=payload,
        supersedes=body.supersedes,
        is_synthetic=True,
    )
    try:
        async with _scope(request) as session:
            return await EvidenceService(session).append(event)
    except EvidenceValidationError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "evento inválido") from None


@router.get("/projects/{project_id}/evidence", response_model=list[EvidenceEvent])
async def list_evidence(
    project_id: UUID,
    request: Request,
    kind: Annotated[list[EventKind] | None, Query()] = None,
) -> list[EvidenceEvent]:
    async with _scope(request) as session:
        return await EvidenceService(session).query(
            request.app.state.settings.tenant_id, project_id=project_id, kinds=kind, limit=200
        )
