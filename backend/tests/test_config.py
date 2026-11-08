"""Testes de validação de configuração no startup."""

from uuid import UUID

import pytest

from basho.config import ConfigError, load_settings
from basho.main import create_app


@pytest.mark.parametrize("missing", ["DATABASE_URL", "ANTHROPIC_API_KEY", "TENANT_ID"])
def test_app_does_not_start_without_required_variable(
    valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    # Arrange
    monkeypatch.delenv(missing)

    # Act / Assert
    with pytest.raises(ConfigError, match=missing):
        create_app()


def test_config_error_does_not_leak_secret_values(
    valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    monkeypatch.delenv("GITHUB_TOKEN")
    monkeypatch.setenv("FEATHERLESS_BASE_URL", "not-a-url-with-secret-xyz")

    # Act
    with pytest.raises(ConfigError) as exc_info:
        load_settings()

    # Assert
    message = str(exc_info.value)
    assert "GITHUB_TOKEN" in message
    assert "FEATHERLESS_BASE_URL" in message
    assert exc_info.value.__cause__ is None
    for value in [*valid_env.values(), "not-a-url-with-secret-xyz"]:
        assert value not in message


def test_settings_repr_masks_secrets(valid_env: dict[str, str]) -> None:
    # Arrange
    settings = load_settings()

    # Act
    rendered = repr(settings)

    # Assert
    assert valid_env["ANTHROPIC_API_KEY"] not in rendered
    assert valid_env["GITHUB_TOKEN"] not in rendered
    assert valid_env["DATABASE_URL"] not in rendered


def test_tenant_id_is_parsed_as_uuid(valid_env: dict[str, str]) -> None:
    # Arrange
    expected = UUID(valid_env["TENANT_ID"])

    # Act
    settings = load_settings()

    # Assert
    assert settings.tenant_id == expected


def test_app_does_not_start_with_invalid_tenant_id(
    valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    monkeypatch.setenv("TENANT_ID", "not-a-uuid")

    # Act / Assert
    with pytest.raises(ConfigError, match="TENANT_ID"):
        create_app()


def test_maker_model_defaults_to_opus_with_high_effort(valid_env: dict[str, str]) -> None:
    # Act
    settings = load_settings()

    # Assert
    assert (settings.maker_model, settings.maker_effort) == ("claude-opus-5-5", "high")


def test_app_does_not_start_when_maker_and_checker_are_the_same_model(
    valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange: ADR-0004 exige Checker de outro modelo
    monkeypatch.setenv("MAKER_MODEL", valid_env["CHECKER_MODEL"].upper())

    # Act / Assert
    with pytest.raises(ConfigError):
        load_settings()
