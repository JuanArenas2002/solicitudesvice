from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, password_hash: str, password: str) -> bool: ...

    def needs_rehash(self, password_hash: str) -> bool: ...

    def verify_dummy(self, password: str) -> None:
        """Gasta el mismo tiempo que verify() para no revelar si un usuario existe."""
        ...


@dataclass(frozen=True, slots=True)
class AccessToken:
    value: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class AccessClaims:
    user_id: UUID
    session_id: UUID


class AccessTokenService(Protocol):
    def issue(self, user_id: UUID, session_id: UUID, now: datetime) -> AccessToken: ...

    def decode(self, token: str) -> AccessClaims:
        """Valida firma y expiración. Lanza Unauthorized si el token no es válido."""
        ...


class RefreshTokenGenerator(Protocol):
    def generate(self) -> str:
        """Token opaco de alta entropía (se entrega al cliente una sola vez)."""
        ...

    def hash(self, raw_token: str) -> str:
        """Hash SHA-256 en hexadecimal: lo único que se persiste."""
        ...


class CsrfTokenService(Protocol):
    def issue(self, refresh_token: str) -> str: ...

    def verify(self, refresh_token: str, csrf_token: str) -> bool: ...
