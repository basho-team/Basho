"""Módulo audit: log imutável de ações de agente e humano. Outros módulos usam só esta API."""

from basho.audit.contracts import (
    ActorType,
    AuditDecision,
    AuditEntry,
    AuditEventType,
    AuditOutcome,
    InputSummary,
    NewAuditEntry,
)
from basho.audit.service import AuditError, AuditService, AuditSink, InMemoryAuditLog

__all__ = [
    "ActorType",
    "AuditDecision",
    "AuditEntry",
    "AuditError",
    "AuditEventType",
    "AuditOutcome",
    "AuditService",
    "AuditSink",
    "InMemoryAuditLog",
    "InputSummary",
    "NewAuditEntry",
]
