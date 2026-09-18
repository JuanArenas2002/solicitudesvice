from dataclasses import dataclass
from datetime import datetime

from app.domain.entities.user import User


@dataclass(frozen=True, slots=True)
class SessionTokens:
    """Par de tokens de una sesión. El refresh token va en cookie HttpOnly, nunca en el cuerpo."""

    access_token: str
    access_expires_at: datetime
    refresh_token: str
    refresh_expires_at: datetime


@dataclass(frozen=True, slots=True)
class LoginResult:
    tokens: SessionTokens
    user: User


@dataclass(frozen=True, slots=True)
class AuthConfig:
    """Política de duración de sesiones (la application no conoce Settings)."""

    refresh_token_ttl_seconds: int
    session_max_lifetime_seconds: int
