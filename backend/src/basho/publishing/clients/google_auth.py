"""Token de acesso do Google a partir de uma service account (JWT bearer, RFC 7523).

O usuário compartilha a pasta com o e-mail da service account (papel Editor); o Basho assina um
JWT RS256 com a chave privada (variável de ambiente, ADR-0006) e troca por um access token de
curta duração. Nada é gravado em disco nem logado.
"""

from __future__ import annotations

import base64
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from basho.publishing.clients.errors import ProviderError, ProviderErrorCode, error_from_status

DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"
TOKEN_URI = "https://oauth2.googleapis.com/token"  # noqa: S105 -- endpoint público, não segredo
JWT_LIFETIME_SECONDS = 3600
REFRESH_MARGIN_SECONDS = 120
_GRANT = "urn:ietf:params:oauth:grant-type:jwt-bearer"


class TokenSource(Protocol):
    async def token(self) -> str: ...


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


@dataclass(frozen=True, slots=True)
class ServiceAccountInfo:
    client_email: str
    private_key: str

    @classmethod
    def parse(cls, raw: str) -> ServiceAccountInfo:
        """Aceita o JSON da chave ou o caminho de um arquivo `.json`."""
        text = raw.strip()
        try:
            content = text if text.startswith("{") else Path(text).read_text(encoding="utf-8")
            data = json.loads(content)
            email, key = data["client_email"], data["private_key"]
        except (OSError, ValueError, KeyError, TypeError):
            raise ProviderError(ProviderErrorCode.NOT_CONFIGURED) from None
        if not isinstance(email, str) or not isinstance(key, str) or "@" not in email:
            raise ProviderError(ProviderErrorCode.NOT_CONFIGURED)
        return cls(client_email=email, private_key=key)


class ServiceAccountTokens:
    """Cache do access token; renova antes de expirar."""

    def __init__(
        self,
        info: ServiceAccountInfo,
        http: httpx.AsyncClient,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._info = info
        self._http = http
        self._clock = clock
        self._cached: tuple[str, float] | None = None

    @property
    def email(self) -> str:
        return self._info.client_email

    def _assertion(self, now: int) -> str:
        header = _b64(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
        claims = _b64(
            json.dumps(
                {
                    "iss": self._info.client_email,
                    "scope": DRIVE_SCOPE,
                    "aud": TOKEN_URI,
                    "iat": now,
                    "exp": now + JWT_LIFETIME_SECONDS,
                }
            ).encode()
        )
        signing_input = f"{header}.{claims}".encode("ascii")
        try:
            key = serialization.load_pem_private_key(self._info.private_key.encode(), password=None)
        except (ValueError, TypeError):
            raise ProviderError(ProviderErrorCode.NOT_CONFIGURED) from None
        if not isinstance(key, rsa.RSAPrivateKey):
            raise ProviderError(ProviderErrorCode.NOT_CONFIGURED)
        signature = key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
        return f"{header}.{claims}.{_b64(signature)}"

    async def token(self) -> str:
        now = self._clock()
        if self._cached is not None and now < self._cached[1] - REFRESH_MARGIN_SECONDS:
            return self._cached[0]
        try:
            response = await self._http.post(
                TOKEN_URI,
                data={"grant_type": _GRANT, "assertion": self._assertion(int(now))},
                timeout=15.0,
            )
        except httpx.HTTPError:
            raise ProviderError(ProviderErrorCode.UNAVAILABLE, retryable=True) from None
        if response.status_code != httpx.codes.OK:
            # 400 invalid_grant = chave revogada/relógio errado: não adianta repetir.
            raise error_from_status(response.status_code)
        try:
            payload = response.json()
            access, lifetime = str(payload["access_token"]), float(payload.get("expires_in", 3600))
        except (ValueError, KeyError, TypeError):
            raise ProviderError(ProviderErrorCode.UNEXPECTED) from None
        self._cached = (access, now + lifetime)
        return access
