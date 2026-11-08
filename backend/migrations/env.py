"""Ambiente Alembic assíncrono (SQLAlchemy 2 + psycopg 3).

A URL vem só de ``DATABASE_URL`` (sem carregar ``Settings``, que exige todas as chaves).
Migrações rodam via CLI (``uv run alembic upgrade head``), nunca no startup da API.
"""

import asyncio
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Sem autogenerate: migrações são escritas à mão com SQL explícito.
target_metadata = None


def _database_url() -> str:
    """Lê DATABASE_URL; a mensagem de erro nunca inclui o valor."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        message = "DATABASE_URL não definida; exporte-a antes de rodar o Alembic."
        raise RuntimeError(message)
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = create_async_engine(_database_url(), poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    # psycopg async não funciona com o ProactorEventLoop padrão do Windows.
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    asyncio.run(run_async_migrations(), loop_factory=loop_factory)
