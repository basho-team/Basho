"""`POST /api/v1/projects/{id}/evidence/{event_id}/correction`: corrigir evidência e propagar."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from basho.evidence.correction import EvidenceCorrectionService
from basho.evidence.domain.rules import EvidenceNotFoundError, EvidenceValidationError
from basho.evidence.propagation import PropagationResult
from basho.identity import HumanIdentity, current_human
from basho.reports.api import _scope

router = APIRouter(prefix="/projects", tags=["evidence"])


class EvidenceCorrectionIn(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)
    description: str = Field(min_length=10, max_length=4000)
    reason: str = Field(min_length=10, max_length=1000)


@router.post(
    "/{project_id}/evidence/{event_id}/correction",
    response_model=PropagationResult,
    status_code=status.HTTP_201_CREATED,
)
async def correct_evidence(
    project_id: UUID,
    event_id: UUID,
    body: EvidenceCorrectionIn,
    request: Request,
    human: Annotated[HumanIdentity, Depends(current_human)],
) -> PropagationResult:
    """Ação humana: grava a correção (supersedes) e propaga needs_review na mesma transação."""
    try:
        async with _scope(request) as session:
            return await EvidenceCorrectionService(session).correct(
                request.app.state.settings.tenant_id,
                project_id,
                event_id,
                description=body.description,
                reason=body.reason,
                author_id=human.user_id,
                author_role=human.role.value,
            )
    except EvidenceNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "evidência não encontrada") from None
    except EvidenceValidationError:
        msg = "correção não permitida para esta evidência"
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, msg) from None
