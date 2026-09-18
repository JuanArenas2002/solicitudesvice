from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_SECRET_LENGTH = 32


class Settings(BaseSettings):
    """Configuración tipada; solo desde variables de entorno (o .env). Sin secretos por defecto."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"

    database_url: str
    db_pool_size: int = Field(10, ge=1, le=100)
    db_max_overflow: int = Field(10, ge=0, le=100)

    jwt_secret_key: SecretStr
    jwt_algorithm: Literal["HS256"] = "HS256"
    jwt_access_token_expire_minutes: int = Field(15, ge=1, le=60)
    jwt_refresh_token_expire_days: int = Field(7, ge=1, le=90)
    session_max_lifetime_days: int = Field(30, ge=1, le=365)

    cookie_secure: bool = True
    cookie_samesite: Literal["strict", "lax"] = "strict"
    cookie_domain: str | None = None
    cors_origins: list[str] = Field(default_factory=list)

    storage_root: str = "storage"  # carpeta raíz de los soportes (<cédula>/<producto>/Solicitud N)
    attachment_max_bytes: int = Field(20 * 1024 * 1024, ge=1024, le=200 * 1024 * 1024)
    # Catálogo de revistas que valida los ISSN. Vacío = sin validación (desarrollo sin red).
    journals_url: str = "https://metrik.unisimon.edu.co/revistas/revistas"
    journals_timeout_seconds: float = Field(4.0, gt=0, le=30)

    @model_validator(mode="after")
    def _validate_security(self) -> Self:
        if len(self.jwt_secret_key.get_secret_value()) < MIN_SECRET_LENGTH:
            raise ValueError(f"JWT_SECRET_KEY debe tener al menos {MIN_SECRET_LENGTH} caracteres")
        if self.jwt_refresh_token_expire_days > self.session_max_lifetime_days:
            raise ValueError(
                "JWT_REFRESH_TOKEN_EXPIRE_DAYS no puede superar SESSION_MAX_LIFETIME_DAYS"
            )
        if self.environment == "production":
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE debe ser true en producción")
            if "*" in self.cors_origins:
                raise ValueError("CORS_ORIGINS no puede contener '*' en producción")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # los campos obligatorios vienen del entorno
