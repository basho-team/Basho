"""Provisiona os logins de menor privilégio de um ambiente de deploy (ADR-0006).

Roda como o role dono (``MIGRATION_DATABASE_URL``), **depois** de ``alembic upgrade head``,
e nunca dentro da API ou do worker. Cria (se faltarem) ``basho_api_login`` e
``basho_worker_login`` como membros de ``basho_api``/``basho_worker`` e (re)define as senhas
a partir de ``API_DB_PASSWORD``/``WORKER_DB_PASSWORD``. Idempotente.

Uso::

    python -m basho.provision

Nenhuma mensagem inclui senha ou URL.
"""

import os
import sys
from dataclasses import dataclass

import psycopg
from psycopg import sql

from basho.db import API_ROLE, WORKER_ROLE

MIN_PASSWORD_LENGTH = 24
SQLALCHEMY_DRIVER_PREFIX = "postgresql+psycopg://"


@dataclass(frozen=True)
class LoginSpec:
    login: str
    group: str
    password_env: str


LOGINS = (
    LoginSpec("basho_api_login", API_ROLE, "API_DB_PASSWORD"),
    LoginSpec("basho_worker_login", WORKER_ROLE, "WORKER_DB_PASSWORD"),
)


class ProvisionError(RuntimeError):
    """Configuração ausente ou inválida; a mensagem nunca traz valores."""


def libpq_url(url: str) -> str:
    """Converte a URL do SQLAlchemy (``postgresql+psycopg://``) para a do libpq."""
    if url.startswith(SQLALCHEMY_DRIVER_PREFIX):
        return "postgresql://" + url[len(SQLALCHEMY_DRIVER_PREFIX) :]
    return url


def read_password(env: dict[str, str], name: str) -> str:
    value = env.get(name, "")
    if len(value) < MIN_PASSWORD_LENGTH:
        message = f"{name} ausente ou com menos de {MIN_PASSWORD_LENGTH} caracteres."
        raise ProvisionError(message)
    return value


def ensure_login(cursor: psycopg.Cursor[object], spec: LoginSpec, password: str) -> None:
    cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (spec.login,))
    if cursor.fetchone() is None:
        cursor.execute(
            sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEROLE NOCREATEDB").format(
                sql.Identifier(spec.login)
            )
        )
    cursor.execute(
        sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(
            sql.Identifier(spec.login), sql.Literal(password)
        )
    )
    cursor.execute(
        sql.SQL("GRANT {} TO {}").format(sql.Identifier(spec.group), sql.Identifier(spec.login))
    )


def provision(env: dict[str, str]) -> None:
    url = env.get("MIGRATION_DATABASE_URL", "")
    if not url:
        message = "MIGRATION_DATABASE_URL não definida."
        raise ProvisionError(message)
    passwords = {spec.login: read_password(env, spec.password_env) for spec in LOGINS}
    with psycopg.connect(libpq_url(url), autocommit=True) as connection:
        cursor = connection.cursor()
        for spec in LOGINS:
            ensure_login(cursor, spec, passwords[spec.login])


def main() -> int:
    try:
        provision(dict(os.environ))
    except ProvisionError as error:
        sys.stderr.write(f"provision: {error}\n")
        return 1
    sys.stdout.write("provision: logins da API e do worker prontos\n")
    return 0


if __name__ == "__main__":  # pragma: no cover - processo real
    sys.exit(main())
