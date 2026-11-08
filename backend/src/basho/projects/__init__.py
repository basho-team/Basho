"""Projetos, atividades, pendências, aprovação formal e dossiê (#5).

Outros módulos usam só ``ProjectService`` e os erros exportados aqui (ADR-0001).
"""

from basho.projects.service import (
    ProjectConflictError,
    ProjectError,
    ProjectForbiddenError,
    ProjectNotFoundError,
    ProjectService,
    ProjectViewTooLargeError,
)

__all__ = [
    "ProjectConflictError",
    "ProjectError",
    "ProjectForbiddenError",
    "ProjectNotFoundError",
    "ProjectService",
    "ProjectViewTooLargeError",
]
