import pytest

from basho.provision import (
    MIN_PASSWORD_LENGTH,
    ProvisionError,
    libpq_url,
    provision,
    read_password,
)


def test_libpq_url_strips_sqlalchemy_driver() -> None:
    assert libpq_url("postgresql+psycopg://u:p@h:5432/db") == "postgresql://u:p@h:5432/db"
    assert libpq_url("postgresql://u:p@h/db") == "postgresql://u:p@h/db"


def test_read_password_rejects_short_value_without_leaking_it() -> None:
    with pytest.raises(ProvisionError) as error:
        read_password({"API_DB_PASSWORD": "curta"}, "API_DB_PASSWORD")
    assert "curta" not in str(error.value)


def test_read_password_accepts_long_value() -> None:
    value = "x" * MIN_PASSWORD_LENGTH
    assert read_password({"API_DB_PASSWORD": value}, "API_DB_PASSWORD") == value


def test_provision_requires_migration_url() -> None:
    with pytest.raises(ProvisionError, match="MIGRATION_DATABASE_URL"):
        provision({})


def test_provision_validates_passwords_before_connecting() -> None:
    env = {"MIGRATION_DATABASE_URL": "postgresql://ninguem@127.0.0.1:1/x"}
    with pytest.raises(ProvisionError, match="API_DB_PASSWORD"):
        provision(env)
