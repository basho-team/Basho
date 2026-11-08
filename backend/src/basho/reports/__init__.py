"""Relatórios de pesquisa: versões, correções rastreáveis, revisão e consolidação gerencial.

Domínio puro e determinístico (sem banco, rotas nem LLM). A persistência de `report_versions`
e `report_reviews` é escopo da #39; os tipos aqui são **proposta** para ratificação de contrato
(ver `docs/reports-consolidation.md`). Base: `ResearchReportDraft` (ADR-0009, proposta).

Outros módulos devem importar só daqui (ADR-0001: comunicação via interface pública).
"""

from basho.reports.consolidation import (
    CONSOLIDATION_NOTE,
    InconsistentConsolidationError,
    ManagerConsolidation,
    ReportInput,
    ReviewState,
    SourceRef,
    consolidate,
)
from basho.reports.corrections import (
    CorrectionOp,
    InvalidCorrectionError,
    ReportCorrection,
    apply_correction,
)
from basho.reports.narrative import render_manager_summary
from basho.reports.versions import (
    ItemKind,
    ReportReview,
    ReportVersion,
    ReviewDecision,
    ReviewerNotAllowedError,
    ReviewerRole,
    VersionConflictError,
    create_first_version,
    review_version,
    validate_history,
)

__all__ = [
    "CONSOLIDATION_NOTE",
    "CorrectionOp",
    "InconsistentConsolidationError",
    "InvalidCorrectionError",
    "ItemKind",
    "ManagerConsolidation",
    "ReportCorrection",
    "ReportInput",
    "ReportReview",
    "ReportVersion",
    "ReviewDecision",
    "ReviewState",
    "ReviewerNotAllowedError",
    "ReviewerRole",
    "SourceRef",
    "VersionConflictError",
    "apply_correction",
    "consolidate",
    "create_first_version",
    "render_manager_summary",
    "review_version",
    "validate_history",
]
