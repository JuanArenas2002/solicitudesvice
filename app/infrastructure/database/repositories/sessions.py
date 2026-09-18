from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.domain.entities.auth_session import AuthSession, RefreshToken
from app.infrastructure.database.models.auth import AuthSessionModel, RefreshTokenModel


def _session_entity(model: AuthSessionModel) -> AuthSession:
    return AuthSession(
        id=model.id,
        user_id=model.user_id,
        created_at=model.created_at,
        expires_at=model.expires_at,
        revoked_at=model.revoked_at,
        revoked_reason=model.revoked_reason,
    )


def _token_entity(model: RefreshTokenModel) -> RefreshToken:
    return RefreshToken(
        id=model.id,
        session_id=model.session_id,
        token_hash=model.token_hash,
        created_at=model.created_at,
        expires_at=model.expires_at,
        used_at=model.used_at,
    )


class SqlAlchemyAuthSessionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_session(self, session: AuthSession) -> None:
        self._session.add(
            AuthSessionModel(
                id=session.id,
                user_id=session.user_id,
                created_at=session.created_at,
                expires_at=session.expires_at,
                revoked_at=session.revoked_at,
                revoked_reason=session.revoked_reason,
            )
        )
        self._session.flush()

    def get_session(self, session_id: UUID) -> AuthSession | None:
        model = self._session.get(AuthSessionModel, session_id)
        return _session_entity(model) if model else None

    def save_session(self, session: AuthSession) -> None:
        model = self._session.get(AuthSessionModel, session.id)
        if model is None:
            raise LookupError(f"Sesión {session.id} no existe")
        model.revoked_at = session.revoked_at
        model.revoked_reason = session.revoked_reason
        self._session.flush()

    def add_refresh_token(self, token: RefreshToken) -> None:
        self._session.add(
            RefreshTokenModel(
                id=token.id,
                session_id=token.session_id,
                token_hash=token.token_hash,
                created_at=token.created_at,
                expires_at=token.expires_at,
                used_at=token.used_at,
            )
        )
        self._session.flush()

    def get_refresh_token_for_update(self, token_hash: str) -> RefreshToken | None:
        model = self._session.scalars(
            select(RefreshTokenModel)
            .where(RefreshTokenModel.token_hash == token_hash)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).one_or_none()
        return _token_entity(model) if model else None

    def save_refresh_token(self, token: RefreshToken) -> None:
        model = self._session.get(RefreshTokenModel, token.id)
        if model is None:
            raise LookupError(f"Refresh token {token.id} no existe")
        model.used_at = token.used_at
        self._session.flush()

    def revoke_all_for_user(
        self,
        user_id: UUID,
        now: datetime,
        reason: str,
        except_session_id: UUID | None = None,
    ) -> int:
        statement = (
            update(AuthSessionModel)
            .where(AuthSessionModel.user_id == user_id, AuthSessionModel.revoked_at.is_(None))
            .values(revoked_at=now, revoked_reason=reason)
            .execution_options(synchronize_session=False)
        )
        if except_session_id is not None:
            statement = statement.where(AuthSessionModel.id != except_session_id)
        return self._session.execute(statement).rowcount  # type: ignore[attr-defined,no-any-return]
