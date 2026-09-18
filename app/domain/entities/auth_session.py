from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from app.domain.exceptions.errors import RefreshTokenReuse, Unauthorized


@dataclass(eq=False)
class AuthSession:
    user_id: UUID
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None
    revoked_reason: str | None = None
    id: UUID = field(default_factory=uuid4)

    def is_active(self, now: datetime) -> bool:
        return self.revoked_at is None and now < self.expires_at

    def revoke(self, now: datetime, reason: str) -> None:
        if self.revoked_at is None:  # idempotente: conserva el primer motivo
            self.revoked_at = now
            self.revoked_reason = reason


@dataclass(eq=False)
class RefreshToken:
    """Solo se conoce el hash SHA-256; el valor real nunca se almacena."""

    session_id: UUID
    token_hash: str
    created_at: datetime
    expires_at: datetime
    used_at: datetime | None = None
    id: UUID = field(default_factory=uuid4)

    def consume(self, now: datetime) -> None:
        """Rotación: cada refresh token sirve una vez; reusar uno consumido indica robo."""
        if self.used_at is not None:
            raise RefreshTokenReuse("Refresh token ya utilizado")
        if now >= self.expires_at:
            raise Unauthorized("Refresh token expirado")
        self.used_at = now
