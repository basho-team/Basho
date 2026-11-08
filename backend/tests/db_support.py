"""Helpers de banco para os testes de integração (criação de bancos e Alembic)."""

import os
import secrets
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

import psycopg
import pytest
from psycopg import sql
from sqlalchemy.engine import URL, make_url

BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_DB_PREFIX = "basho_test"
MAINTENANCE_DB_NAME = "postgres"
CONNECT_TIMEOUT_SECONDS = 3
ALEMBIC_TIMEOUT_SECONDS = 120


def skip_or_fail(message: str) -> NoReturn:
    """Pula o teste; com ``REQUIRE_DB_TESTS=1`` (CI) falha em vez de pular."""
    if os.environ.get("REQUIRE_DB_TESTS") == "1":
        pytest.fail(message)
    pytest.skip(message)


def base_url() -> URL:
    raw = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not raw:
        skip_or_fail("TEST_DATABASE_URL/DATABASE_URL não definida; testes de banco pulados")
    return make_url(raw)


def psycopg_dsn(url: URL, database: str) -> str:
    return url.set(drivername="postgresql", database=database).render_as_string(hide_password=False)


def recreate_database(base: URL, name: str) -> URL:
    """Recria um banco de teste. Recusa nomes fora do prefixo ``basho_test``."""
    if not name.startswith(TEST_DB_PREFIX):
        raise ValueError("recusado: só bancos de teste podem ser recriados")
    try:
        admin = psycopg.connect(
            psycopg_dsn(base, MAINTENANCE_DB_NAME),
            autocommit=True,
            connect_timeout=CONNECT_TIMEOUT_SECONDS,
        )
    except psycopg.OperationalError:
        skip_or_fail("Postgres inacessível com a URL de teste; testes de banco pulados")
    with admin:
        admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        admin.execute(f'CREATE DATABASE "{name}"')
    return base.set(database=name)


def provision_login_role(owner: URL, login: str, group: str) -> URL:
    """(Re)cria um usuário de login de teste, membro de ``group``, com senha aleatória.

    Simula o provisionamento feito fora das migrações (ver README). Recusa nomes fora
    do prefixo ``basho_test`` para nunca tocar em roles reais do servidor.
    """
    if not login.startswith(TEST_DB_PREFIX):
        raise ValueError("recusado: só roles de teste podem ser recriados")
    password = secrets.token_urlsafe(24)
    with psycopg.connect(psycopg_dsn(owner, owner.database or MAINTENANCE_DB_NAME)) as admin:
        admin.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(login)))
        admin.execute(
            sql.SQL("CREATE ROLE {} LOGIN INHERIT PASSWORD {} IN ROLE {}").format(
                sql.Identifier(login), sql.Literal(password), sql.Identifier(group)
            )
        )
    return owner.set(username=login, password=password)


def run_alembic(url: URL, *args: str) -> None:
    """Roda o Alembic e falha o teste se o comando falhar."""
    result = run_alembic_raw(url, *args)
    if result.returncode != 0:
        pytest.fail(f"alembic {' '.join(args)} falhou:\n{result.stderr[-2000:]}")


def run_alembic_raw(url: URL, *args: str) -> "subprocess.CompletedProcess[str]":
    """Roda o CLI do Alembic em subprocesso (env.py é async e cria seu próprio loop)."""
    env = {**os.environ, "MIGRATION_DATABASE_URL": url.render_as_string(hide_password=False)}
    return subprocess.run(  # noqa: S603
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=ALEMBIC_TIMEOUT_SECONDS,
        check=False,
    )
