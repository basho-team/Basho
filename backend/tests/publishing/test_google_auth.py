"""JWT bearer da service account: assinatura RS256 verificável e cache do token."""

import base64
import json
from pathlib import Path

import httpx
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from basho.publishing.clients.errors import ProviderError, ProviderErrorCode
from basho.publishing.clients.google_auth import (
    DRIVE_SCOPE,
    TOKEN_URI,
    ServiceAccountInfo,
    ServiceAccountTokens,
)

EMAIL = "basho@projeto-sintetico.iam.gserviceaccount.com"


def _unb64(part: str) -> bytes:
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


@pytest.fixture(scope="module")
def key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _pem(key: rsa.RSAPrivateKey) -> str:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


def _info(key: rsa.RSAPrivateKey) -> ServiceAccountInfo:
    return ServiceAccountInfo(client_email=EMAIL, private_key=_pem(key))


async def test_token_request_carries_a_valid_signed_jwt(key: rsa.RSAPrivateKey) -> None:
    # Arrange
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"access_token": "ya29.sintetico", "expires_in": 3600})

    tokens = ServiceAccountTokens(
        _info(key), httpx.AsyncClient(transport=httpx.MockTransport(handler)), clock=lambda: 1000.0
    )

    # Act
    token = await tokens.token()

    # Assert
    assert token == "ya29.sintetico"  # noqa: S105 -- sintético
    assert str(seen[0].url) == TOKEN_URI
    form = dict(item.split("=", 1) for item in seen[0].content.decode().split("&"))
    assert form["grant_type"].startswith("urn%3Aietf")
    header, claims, signature = form["assertion"].split(".")
    payload = json.loads(_unb64(claims))
    assert payload["iss"] == EMAIL
    assert payload["scope"] == DRIVE_SCOPE
    assert payload["aud"] == TOKEN_URI
    assert payload["exp"] - payload["iat"] == 3600
    assert json.loads(_unb64(header)) == {"alg": "RS256", "typ": "JWT"}
    # a assinatura confere com a chave pública (levanta se não conferir)
    key.public_key().verify(
        _unb64(signature), f"{header}.{claims}".encode(), padding.PKCS1v15(), hashes.SHA256()
    )


async def test_token_is_cached_until_close_to_expiry(key: rsa.RSAPrivateKey) -> None:
    # Arrange
    calls = {"n": 0}
    now = {"t": 1000.0}

    def handler(_: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"access_token": f"t{calls['n']}", "expires_in": 3600})

    tokens = ServiceAccountTokens(
        _info(key),
        httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        clock=lambda: now["t"],
    )

    # Act
    first = await tokens.token()
    now["t"] += 600
    second = await tokens.token()
    now["t"] += 3600  # perto do vencimento: renova
    third = await tokens.token()

    # Assert
    assert (first, second, third) == ("t1", "t1", "t2")


async def test_revoked_key_is_a_permanent_error(key: rsa.RSAPrivateKey) -> None:
    # Arrange
    transport = httpx.MockTransport(lambda _: httpx.Response(400, json={"error": "invalid_grant"}))
    tokens = ServiceAccountTokens(_info(key), httpx.AsyncClient(transport=transport))

    # Act / Assert
    with pytest.raises(ProviderError) as caught:
        await tokens.token()
    assert caught.value.retryable is False


async def test_malformed_private_key_is_reported_as_not_configured() -> None:
    # Arrange
    info = ServiceAccountInfo(client_email=EMAIL, private_key="não é uma chave")
    tokens = ServiceAccountTokens(
        info, httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200)))
    )

    # Act / Assert
    with pytest.raises(ProviderError) as caught:
        await tokens.token()
    assert caught.value.code is ProviderErrorCode.NOT_CONFIGURED


def test_service_account_info_parses_inline_json_and_file(
    key: rsa.RSAPrivateKey, tmp_path: Path
) -> None:
    # Arrange
    raw = json.dumps({"client_email": EMAIL, "private_key": _pem(key)})
    file = tmp_path / "sa.json"
    file.write_text(raw, encoding="utf-8")

    # Act / Assert
    assert ServiceAccountInfo.parse(raw).client_email == EMAIL
    assert ServiceAccountInfo.parse(str(file)).client_email == EMAIL


@pytest.mark.parametrize(
    "raw", ["", "{}", "{nao-json", "/caminho/que/nao/existe.json", '{"client_email": 1}']
)
def test_invalid_service_account_config_is_not_configured(raw: str) -> None:
    # Act / Assert
    with pytest.raises(ProviderError) as caught:
        ServiceAccountInfo.parse(raw)
    assert caught.value.code is ProviderErrorCode.NOT_CONFIGURED
