from datetime import timedelta
from typing import NoReturn

from app.application.commands.auth import LoginCommand
from app.application.commands.context import RequestContext
from app.application.dto.auth import AuthConfig, LoginResult, SessionTokens
from app.application.ports.repositories.unit_of_work import UnitOfWork, UnitOfWorkFactory
from app.application.ports.services.clock import Clock
from app.application.ports.services.security import (
    AccessTokenService,
    PasswordHasher,
    RefreshTokenGenerator,
)
from app.application.use_cases.audit_helper import record_audit
from app.domain.entities.auth_session import AuthSession, RefreshToken
from app.domain.entities.user import User
from app.domain.enums.audit_action import AuditAction
from app.domain.exceptions.errors import InvalidValue, Unauthorized
from app.domain.value_objects.email import Email

INVALID_CREDENTIALS = "Credenciales inválidas"


class Login:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        hasher: PasswordHasher,
        access_tokens: AccessTokenService,
        refresh_tokens: RefreshTokenGenerator,
        config: AuthConfig,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._hasher = hasher
        self._access_tokens = access_tokens
        self._refresh_tokens = refresh_tokens
        self._config = config

    def execute(self, command: LoginCommand, ctx: RequestContext) -> LoginResult:
        now = self._clock.now()
        with self._uow_factory() as uow:
            user = self._find_user(uow, command.email)
            if user is None:
                self._hasher.verify_dummy(command.password)  # mismo costo: no revela existencia
                self._fail(uow, ctx, "unknown_user", None)
            if not self._hasher.verify(user.password_hash, command.password):
                self._fail(uow, ctx, "bad_password", user)
            if not user.is_active:
                self._fail(uow, ctx, "inactive_user", user)

            if self._hasher.needs_rehash(user.password_hash):
                user.set_password_hash(self._hasher.hash(command.password), now)
            user.record_login(now)
            uow.users.save(user)

            session = AuthSession(
                user_id=user.id,
                created_at=now,
                expires_at=now + timedelta(seconds=self._config.session_max_lifetime_seconds),
            )
            uow.sessions.add_session(session)
            raw_refresh = self._refresh_tokens.generate()
            refresh = RefreshToken(
                session_id=session.id,
                token_hash=self._refresh_tokens.hash(raw_refresh),
                created_at=now,
                expires_at=min(
                    now + timedelta(seconds=self._config.refresh_token_ttl_seconds),
                    session.expires_at,
                ),
            )
            uow.sessions.add_refresh_token(refresh)
            access = self._access_tokens.issue(user.id, session.id, now)
            record_audit(
                uow,
                ctx,
                now,
                AuditAction.LOGIN_SUCCEEDED,
                actor_id=user.id,
                entity_id=session.id,
            )
            uow.commit()
            return LoginResult(
                tokens=SessionTokens(
                    access_token=access.value,
                    access_expires_at=access.expires_at,
                    refresh_token=raw_refresh,
                    refresh_expires_at=refresh.expires_at,
                ),
                user=user,
            )

    @staticmethod
    def _find_user(uow: UnitOfWork, raw_email: str) -> User | None:
        try:
            return uow.users.get_by_email(Email.parse(raw_email))
        except InvalidValue:
            return None  # un email mal formado es simplemente "credenciales inválidas"

    def _fail(
        self, uow: UnitOfWork, ctx: RequestContext, reason: str, user: User | None
    ) -> NoReturn:
        """Audita el intento y CONFIRMA antes de fallar, para que el registro sobreviva."""
        record_audit(
            uow,
            ctx,
            self._clock.now(),
            AuditAction.LOGIN_FAILED,
            actor_id=user.id if user else None,
            entity_id=None,
            detail={"reason": reason},
        )
        uow.commit()
        raise Unauthorized(INVALID_CREDENTIALS)  # mismo mensaje en todos los casos
