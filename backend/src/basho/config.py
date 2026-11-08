"""Configuração tipada carregada de variáveis de ambiente (ADR-0006).

Segredos usam ``SecretStr`` para nunca aparecerem em ``repr``/logs. Se alguma
variável obrigatória faltar ou for inválida, ``load_settings`` levanta
``ConfigError`` com os *nomes* das variáveis problemáticas, nunca os valores.
"""

from functools import lru_cache
from typing import Literal, Self
from uuid import UUID

from pydantic import AnyHttpUrl, Field, SecretStr, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigError(RuntimeError):
    """Configuração ausente ou inválida; a mensagem não contém valores."""


class Settings(BaseSettings):
    """Variáveis de ambiente da aplicação. Obrigatórias, exceto as do Maker (com padrão)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
        case_sensitive=False,
    )

    database_url: SecretStr
    anthropic_api_key: SecretStr
    featherless_api_key: SecretStr
    featherless_base_url: AnyHttpUrl
    checker_model: str
    github_token: SecretStr
    tenant_id: UUID
    maker_model: str = Field(default="claude-opus-5-5", min_length=1)
    maker_effort: Literal["low", "medium", "high", "xhigh", "max"] = "high"

    @model_validator(mode="after")
    def _maker_and_checker_differ(self) -> Self:
        """ADR-0004: o Checker é outro modelo. O fallback Claude do Checker confere o mesmo
        no `ClaudeVerifier(maker_model=...)` (#9)."""
        if self.maker_model.strip().lower() == self.checker_model.strip().lower():
            raise ValueError("MAKER_MODEL e CHECKER_MODEL precisam ser modelos diferentes")
        return self


def _describe_errors(error: ValidationError) -> str:
    """Resume erros de validação citando apenas nomes de variáveis e o tipo do erro."""
    problems = sorted(
        {
            f"{'.'.join(str(part) for part in item['loc']).upper()} ({item['type']})"
            for item in error.errors(include_input=False, include_url=False)
        }
    )
    return ", ".join(problems)


def load_settings() -> Settings:
    """Carrega e valida a configuração, falhando com mensagem clara e sem valores."""
    try:
        return Settings()
    except ValidationError as exc:
        message = f"Configuração inválida ou ausente: {_describe_errors(exc)}"
        raise ConfigError(message) from None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Retorna a configuração validada (cacheada por processo)."""
    return load_settings()
