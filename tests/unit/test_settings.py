import pytest
from pydantic import ValidationError

from app.config.settings import Settings

BASE = {"database_url": "postgresql+psycopg://u:p@localhost/db", "jwt_secret_key": "s" * 32}


def make(**overrides) -> Settings:
    return Settings(_env_file=None, **{**BASE, **overrides})  # type: ignore[call-arg]


def test_defaults_are_safe() -> None:
    settings = make()
    assert settings.environment == "development"
    assert settings.cookie_secure is True and settings.cookie_samesite == "strict"
    assert settings.jwt_access_token_expire_minutes == 15
    assert "s" * 32 not in repr(settings)  # el secreto no se imprime


def test_secrets_have_no_default() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


@pytest.mark.parametrize(
    "overrides",
    [
        {"jwt_secret_key": "corta"},
        {"jwt_access_token_expire_minutes": 0},
        {"jwt_access_token_expire_minutes": 600},
        {"jwt_refresh_token_expire_days": 60, "session_max_lifetime_days": 30},
        {"environment": "production", "cookie_secure": False},
        {"environment": "production", "cors_origins": ["*"]},
        {"db_pool_size": 0},
    ],
)
def test_invalid_configuration_is_rejected(overrides) -> None:
    with pytest.raises(ValidationError):
        make(**overrides)


def test_production_with_strict_settings_is_valid() -> None:
    settings = make(
        environment="production", cookie_secure=True, cors_origins=["https://app.example.org"]
    )
    assert settings.environment == "production"


def test_reads_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://a:b@db/x")
    monkeypatch.setenv("JWT_SECRET_KEY", "k" * 40)
    monkeypatch.setenv("CORS_ORIGINS", '["https://app.example.org"]')
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.database_url.endswith("/x")
    assert settings.cors_origins == ["https://app.example.org"]
