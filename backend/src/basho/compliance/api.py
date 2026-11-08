"""Rota do dossiê fiscal (`/api/v1/projects/{id}/dossier`). Insumo para análise humana."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status

from basho.compliance.dossier_service import DossierService, EmptyDossierError
from basho.compliance.report_evidence import ReportEvidenceDossier, ScopeMismatchError
from basho.reports.api import _scope
from basho.reports.journey_api import Period

router = APIRouter(tags=["compliance"])


@router.get("/projects/{project_id}/dossier", response_model=ReportEvidenceDossier)
async def get_dossier(
    project_id: UUID,
    period: Period,
    request: Request,
    fiscal_year: Annotated[int, Query(ge=2005, le=9999)],
) -> ReportEvidenceDossier:
    try:
        async with _scope(request) as session:
            return await DossierService(session).build(
                request.app.state.settings.tenant_id, project_id, period, fiscal_year
            )
    except EmptyDossierError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "nenhum relatório no período") from None
    except ScopeMismatchError:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "fora do escopo autorizado") from None
