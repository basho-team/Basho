"""Identidade humana nos endpoints de ação humana/formal (placeholder até #47).

Compartilhado por `reports` (#39) e `projects` (#5): mesmos headers, mesmo segredo do BFF.
"""

import hmac
from enum import StrEnum
from uuid import UUID

from fastapi import Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, SecretStr

USER_ID_HEADER = "X-Basho-User-Id"
ROLE_HEADER = "X-Basho-Role"
IDENTITY_SECRET_HEADER = "X-Basho-Identity-Secret"  # noqa: S105 -- nome do header
UNAUTHORIZED_DETAIL = "identidade do revisor ausente ou não confiável"
UNAVAILABLE_DETAIL = "ação humana indisponível: identidade do revisor não configurada"


class HumanRole(StrEnum):
    RESEARCHER = "researcher"
    MANAGER = "manager"


class HumanIdentity(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: UUID
    role: HumanRole


def _configured_secret(request: Request) -> str:
    secret: SecretStr | None = request.app.state.settings.reviewer_identity_secret
    value = "" if secret is None else secret.get_secret_value()
    if not value:  # vazio conta como ausente: nunca aceitar header vazio
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=UNAVAILABLE_DETAIL)
    return value


def current_human(
    request: Request,
    user_id: str | None = Header(default=None, alias=USER_ID_HEADER),
    role: str | None = Header(default=None, alias=ROLE_HEADER),
    identity_secret: str | None = Header(default=None, alias=IDENTITY_SECRET_HEADER),
) -> HumanIdentity:
    """Só aceita `X-Basho-User-Id`/`X-Basho-Role` vindos do BFF que conhece
    `REVIEWER_IDENTITY_SECRET` (comparação em tempo constante). Sem segredo configurado, a ação
    fica fechada (503). A identidade é *afirmada* pelo BFF, não verificada aqui; por isso os
    eventos do ledger gravam ``identity_verified: false``.
    """
    expected = _configured_secret(request)
    provided = identity_secret or ""
    if not hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=UNAUTHORIZED_DETAIL)
    try:
        if user_id is None or role is None:
            raise ValueError
        return HumanIdentity(user_id=UUID(user_id), role=HumanRole(role))
    except ValueError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=UNAUTHORIZED_DETAIL) from None
