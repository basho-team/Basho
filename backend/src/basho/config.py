"""Configuração tipada carregada de variáveis de ambiente (ADR-0006).

Segredos usam ``SecretStr`` para nunca aparecerem em ``repr``/logs. Se alguma
variável obrigatória faltar ou for inválida, ``load_settings`` levanta
``ConfigError`` com os *nomes* das variáveis problemáticas, nunca os valores.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal, Self
from uuid import UUID

from pydantic import AnyHttpUrl, Field, SecretStr, ValidationError, field_validator, model_validator
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
    featherless_fallback_api_key: SecretStr | None = None
    """Segunda conta do Featherless, usada quando a primária fica sem crédito (401/402/403)."""
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

    maker_provider: Literal["anthropic", "featherless"] = "anthropic"
    """`featherless` = Maker via API compatível com OpenAI em `FEATHERLESS_BASE_URL` (ADR-0011)."""
    maker_model: str = Field(default="claude-opus-5-5", min_length=1)
    checker_fallback_model: str | None = None
    """Fallback do Checker no mesmo provedor OpenAI-compatível (ex.: outro modelo do
    Featherless). Sem ele e com Maker no Featherless, o fallback Claude não é usado."""
    maker_effort: Literal["low", "medium", "high", "xhigh", "max"] = "high"
    github_fixtures_dir: Path | None = None
    """Fixtures sintéticas do GitHub para as tools simuladas (projeto sem repositório)."""
    github_project_repos: dict[UUID, str] = Field(default_factory=dict)
    """`GITHUB_PROJECT_REPOS` (JSON `{project_id: "owner/name"}`): projetos com GitHub real
    no worker. Projeto fora do mapa usa as tools simuladas (até o projeto guardar o repo)."""
    google_drive_client_id: str = ""
    """OAuth do Google Drive (ADR-0010), escopo `drive.readonly`. Sem os três valores e o mapa
    de pastas, o Drive fica desligado."""
    google_drive_client_secret: SecretStr | None = None
    google_drive_refresh_token: SecretStr | None = None
    google_drive_project_folders: dict[UUID, list[str]] = Field(default_factory=dict)
    """`GOOGLE_DRIVE_PROJECT_FOLDERS` (JSON `{project_id: ["<folder_id>", ...]}`)."""
    notion_token: SecretStr | None = None
    """Token de integração interna do Notion (ADR-0010); só lê o que foi compartilhado."""
    notion_project_sources: dict[UUID, list[str]] = Field(default_factory=dict)
    """`NOTION_PROJECT_SOURCES` (JSON `{project_id: ["database:<id>", "page:<id>"]}`)."""

    @field_validator(
        "google_drive_client_secret",
        "google_drive_refresh_token",
        "notion_token",
        "featherless_fallback_api_key",
    )
    @classmethod
    def _empty_secret_is_none(cls, value: SecretStr | None) -> SecretStr | None:
        return None if value is None or not value.get_secret_value().strip() else value

    @model_validator(mode="after")
    def _maker_and_checker_differ(self) -> Self:
        """ADR-0004: o Checker é outro modelo. O fallback Claude do Checker confere o mesmo
        no `ClaudeVerifier(maker_model=...)` (#9)."""
        if self.maker_model.strip().lower() == self.checker_model.strip().lower():
            raise ValueError("MAKER_MODEL e CHECKER_MODEL precisam ser modelos diferentes")
        fallback = (self.checker_fallback_model or "").strip().lower()
        if fallback and fallback == self.maker_model.strip().lower():
            raise ValueError("MAKER_MODEL e CHECKER_FALLBACK_MODEL precisam ser modelos diferentes")
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
