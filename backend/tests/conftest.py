"""Fixtures compartilhadas."""

import asyncio
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from basho.config import get_settings

if sys.platform == "win32":  # psycopg async não funciona com o ProactorEventLoop
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

VALID_ENV: dict[str, str] = {
    "DATABASE_URL": "postgresql+psycopg://basho:test-db-secret@localhost:5432/basho",
    "ANTHROPIC_API_KEY": "test-anthropic-secret",
    "FEATHERLESS_API_KEY": "test-featherless-secret",
    "FEATHERLESS_BASE_URL": "https://featherless.example.test/v1",
    "CHECKER_MODEL": "test-checker-model",
    "GITHUB_TOKEN": "test-github-secret",
    "TENANT_ID": "00000000-0000-0000-0000-000000000001",
}


@pytest.fixture
def isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Remove as variáveis da app do ambiente e isola de qualquer ``.env`` local."""
    for name in VALID_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def valid_env(isolated_env: None, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Define um ambiente completo e válido com valores sintéticos."""
    for name, value in VALID_ENV.items():
        monkeypatch.setenv(name, value)
    return VALID_ENV


@pytest.fixture(autouse=True)
def clear_settings_cache() -> Iterator[None]:
    """Garante que cada teste carregue a configuração do zero."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
