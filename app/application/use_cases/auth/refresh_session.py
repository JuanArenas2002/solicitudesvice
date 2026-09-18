from datetime import timedelta

from app.application.commands.auth import RefreshCommand
from app.application.commands.context import RequestContext
from app.application.dto.auth import AuthConfig, SessionTokens
from app.application.ports.repositories.unit_of_work import UnitOfWorkFactory
from app.application.ports.services.clock import Clock
from app.application.ports.services.security import AccessTokenService, RefreshTokenGenerator
from app.application.use_cases.audit_helper import record_audit
from app.domain.entities.auth_session import RefreshToken
from app.domain.enums.audit_action import AuditAction
from app.domain.exceptions.errors import RefreshTokenReuse, Unauthorized

INVALID_SESSION = "Sesión inválida"


class RefreshSession:
    """Rota el refresh token: cada uno sirve una vez. Reusar uno consumido revoca la sesión."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        access_tokens: AccessTokenService,
        refresh_tokens: RefreshTokenGenerator,
        config: AuthConfig,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._access_tokens = access_tokens
        self._refresh_tokens = refresh_tokens
        self._config = config

    def execute(self, command: RefreshCommand, ctx: RequestContext) -> SessionTokens:
        now = self._clock.now()
        token_hash = self._refresh_tokens.hash(command.refresh_token)
        with self._uow_factory() as uow:
            stored = uow.sessions.get_refresh_token_for_update(token_hash)  # lock de fila
            if stored is None:
                raise Unauthorized(INVALID_SESSION)
            session = uow.sessions.get_session(stored.session_id)
            user = uow.users.get(session.user_id) if session else None
            if session is None or user is None or not session.is_active(now) or not user.is_active:
                raise Unauthorized(INVALID_SESSION)

            try:
                stored.consume(now)
            except RefreshTokenReuse:
                # Posible robo: se revoca la sesión y se CONFIRMA el registro antes de fallar.
                session.revoke(now, "REFRESH_REUSE")
                uow.sessions.save_session(session)
                record_audit(
                    uow,
                    ctx,
                    now,
                    AuditAction.REFRESH_REUSE_DETECTED,
                    actor_id=user.id,
                    entity_id=session.id,
                )
                uow.commit()
                raise
            uow.sessions.save_refresh_token(stored)

            raw = self._refresh_tokens.generate()
            new_token = RefreshToken(
                session_id=session.id,
                token_hash=self._refresh_tokens.hash(raw),
                created_at=now,
                expires_at=min(
                    now + timedelta(seconds=self._config.refresh_token_ttl_seconds),
                    session.expires_at,
                ),
            )
            uow.sessions.add_refresh_token(new_token)
            access = self._access_tokens.issue(user.id, session.id, now)
            uow.commit()
            return SessionTokens(
                access_token=access.value,
                access_expires_at=access.expires_at,
                refresh_token=raw,
                refresh_expires_at=new_token.expires_at,
            )
