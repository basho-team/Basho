"""Helpers de banco para os testes de integração (criação de bancos e Alembic)."""

import os
import subprocess
import sys
from pathlib import Path

import psycopg
import pytest
from sqlalchemy.engine import URL, make_url

BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_DB_PREFIX = "basho_test"
MAINTENANCE_DB_NAME = "postgres"
CONNECT_TIMEOUT_SECONDS = 3
ALEMBIC_TIMEOUT_SECONDS = 120


def base_url() -> URL:
    raw = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not raw:
        pytest.skip("TEST_DATABASE_URL/DATABASE_URL não definida; testes de banco pulados")
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
        pytest.skip("Postgres inacessível com a URL de teste; testes de banco pulados")
    with admin:
        admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        admin.execute(f'CREATE DATABASE "{name}"')
    return base.set(database=name)


def run_alembic(url: URL, *args: str) -> None:
    """Roda o CLI do Alembic em subprocesso (env.py é async e cria seu próprio loop)."""
    env = {**os.environ, "DATABASE_URL": url.render_as_string(hide_password=False)}
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=ALEMBIC_TIMEOUT_SECONDS,
        check=False,
    )
    if result.returncode != 0:
        pytest.fail(f"alembic {' '.join(args)} falhou:\n{result.stderr[-2000:]}")
