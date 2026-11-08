"""Erros estáveis dos provedores de publicação (Drive, Notion). Sem segredo na mensagem."""

from __future__ import annotations

from enum import StrEnum

import httpx


class ProviderErrorCode(StrEnum):
    NOT_CONFIGURED = "not_configured"
    UNAUTHORIZED = "unauthorized"
    ACCESS_DENIED = "access_denied"
    NOT_FOUND = "not_found"
    NOT_A_FOLDER = "not_a_folder"
    RATE_LIMITED = "rate_limited"
    UNAVAILABLE = "unavailable"
    BAD_REQUEST = "bad_request"
    UNEXPECTED = "unexpected"


class ProviderError(RuntimeError):
    """Falha de provedor externo com código estável; `retryable` guia o worker."""

    def __init__(self, code: ProviderErrorCode, *, retryable: bool = False) -> None:
        super().__init__(code.value)
        self.code = code
        self.retryable = retryable


def error_from_status(status_code: int) -> ProviderError:
    """Traduz o status HTTP do provedor; o corpo da resposta nunca vira mensagem."""
    if status_code == httpx.codes.UNAUTHORIZED:
        return ProviderError(ProviderErrorCode.UNAUTHORIZED)
    if status_code == httpx.codes.FORBIDDEN:
        return ProviderError(ProviderErrorCode.ACCESS_DENIED)
    if status_code == httpx.codes.NOT_FOUND:
        return ProviderError(ProviderErrorCode.NOT_FOUND)
    if status_code == httpx.codes.TOO_MANY_REQUESTS:
        return ProviderError(ProviderErrorCode.RATE_LIMITED, retryable=True)
    if status_code >= httpx.codes.INTERNAL_SERVER_ERROR:
        return ProviderError(ProviderErrorCode.UNAVAILABLE, retryable=True)
    if 400 <= status_code < 500:
        return ProviderError(ProviderErrorCode.BAD_REQUEST)
    return ProviderError(ProviderErrorCode.UNEXPECTED)
