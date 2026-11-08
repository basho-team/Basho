"""Configuração tipada carregada de variáveis de ambiente (ADR-0006).

Segredos usam ``SecretStr`` para nunca aparecerem em ``repr``/logs. Se alguma
variável obrigatória faltar ou for inválida, ``load_settings`` levanta
``ConfigError`` com os *nomes* das variáveis problemáticas, nunca os valores.
"""

from functools import lru_cache
from uuid import UUID

from pydantic import AnyHttpUrl, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_IDENTITY_SECRET_LENGTH = 32


class ConfigError(RuntimeError):
    """Configuração ausente ou inválida; a mensagem não contém valores."""


class Settings(BaseSettings):
    """Variáveis de ambiente da aplicação. Todas são obrigatórias, exceto as com padrão."""

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
    # Segredo server-to-server do BFF que repassa a identidade do revisor (#39). Sem ele,
    # endpoints formais de revisão ficam fechados (503). Placeholder até a auth real.
    reviewer_identity_secret: SecretStr | None = None

    @field_validator("reviewer_identity_secret")
    @classmethod
    def _identity_secret_is_strong(cls, value: SecretStr | None) -> SecretStr | None:
        """Vazio = não configurado (revisão fechada); curto demais derruba o startup."""
        if value is None or not value.get_secret_value():
            return None
        if len(value.get_secret_value()) < MIN_IDENTITY_SECRET_LENGTH:
            msg = f"precisa de ao menos {MIN_IDENTITY_SECRET_LENGTH} caracteres"
            raise ValueError(msg)
        return value


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
