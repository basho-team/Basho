"""Módulo publishing: links autorizados e publicação autônoma em Drive e Notion (ADR-0010).

Outros módulos usam só este service público; clientes de provedor ficam em ``clients/``.
"""

from basho.publishing.destinations import Destination, IntegrationRegistry, PublishedDoc
from basho.publishing.links import InvalidLinkError, LinkKind, ParsedLink, parse_link
from basho.publishing.service import PublishingService
from basho.publishing.worker import PublicationWorker

__all__ = [
    "Destination",
    "IntegrationRegistry",
    "InvalidLinkError",
    "LinkKind",
    "ParsedLink",
    "PublicationWorker",
    "PublishedDoc",
    "PublishingService",
    "parse_link",
]
