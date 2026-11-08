"""Módulo evidence: Evidence Ledger. Outros módulos usam só este service público."""

from basho.evidence.domain.rules import (
    EvidenceError,
    EvidenceNotFoundError,
    EvidenceValidationError,
)
from basho.evidence.propagation import (
    CorrectionPropagation,
    PendingReview,
    PropagationResult,
    ReviewMark,
)
from basho.evidence.service import MAX_PAGE_SIZE, EvidenceService

__all__ = [
    "MAX_PAGE_SIZE",
    "CorrectionPropagation",
    "EvidenceError",
    "EvidenceNotFoundError",
    "EvidenceService",
    "EvidenceValidationError",
    "PendingReview",
    "PropagationResult",
    "ReviewMark",
]
