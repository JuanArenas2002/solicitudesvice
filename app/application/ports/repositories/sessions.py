from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.domain.entities.auth_session import AuthSession, RefreshToken


class AuthSessionRepository(Protocol):
    def add_session(self, session: AuthSession) -> None: ...

    def get_session(self, session_id: UUID) -> AuthSession | None: ...

    def save_session(self, session: AuthSession) -> None: ...

    def add_refresh_token(self, token: RefreshToken) -> None: ...

    def get_refresh_token_for_update(self, token_hash: str) -> RefreshToken | None:
        """Bloquea la fila hasta el fin de la transacción: serializa refresh concurrentes."""
        ...

    def save_refresh_token(self, token: RefreshToken) -> None: ...

    def revoke_all_for_user(
        self,
        user_id: UUID,
        now: datetime,
        reason: str,
        except_session_id: UUID | None = None,
    ) -> int:
        """Revoca las sesiones vivas del usuario (salvo una). Devuelve cuántas revocó."""
        ...
