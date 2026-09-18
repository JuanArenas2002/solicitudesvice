"""Flujo completo de autenticación y gestión de usuarios con adaptadores REALES:
PostgreSQL + Argon2id + JWT + tokens opacos. Incluye la carrera de refresh concurrentes."""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.application.commands.auth import ChangePasswordCommand, LoginCommand, RefreshCommand
from app.application.commands.context import RequestContext
from app.application.commands.users import (
    CreateUserCommand,
    ResetPasswordCommand,
    SetUserActiveCommand,
)
from app.application.dto.auth import AuthConfig, SessionTokens
from app.application.use_cases.auth.authenticate import AuthenticateAccessToken
from app.application.use_cases.auth.change_password import ChangeOwnPassword
from app.application.use_cases.auth.login import Login
from app.application.use_cases.auth.logout import Logout
from app.application.use_cases.auth.refresh_session import RefreshSession
from app.application.use_cases.users.manage_users import CreateUser, ResetPassword, SetUserActive
from app.domain.entities.user import User
from app.domain.enums.audit_action import AuditAction
from app.domain.enums.role import Role
from app.domain.exceptions.errors import DuplicateEmail, RefreshTokenReuse, Unauthorized
from app.domain.value_objects.actor import Actor
from app.infrastructure.clock import SystemClock
from app.infrastructure.database.catalog import AUDIT_ACTION_IDS
from app.infrastructure.database.models import (
    AuditLogModel,
    AuthSessionModel,
    RefreshTokenModel,
    UserModel,
)
from app.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork
from app.infrastructure.security.access_tokens import JwtAccessTokenService
from app.infrastructure.security.passwords import Argon2PasswordHasher
from app.infrastructure.security.refresh_tokens import SecureRefreshTokenGenerator

pytestmark = pytest.mark.integration

CTX = RequestContext(correlation_id="it-1", ip_address="198.51.100.20")
PASSWORD = "clave-inicial-segura-1"
NEW_PASSWORD = "clave-nueva-segura-2"


class Stack:
    """Casos de uso ensamblados con los adaptadores reales (lo que hará la composition root)."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory
        self.uow = lambda: SqlAlchemyUnitOfWork(session_factory)
        self.clock = SystemClock()
        self.hasher = Argon2PasswordHasher()
        self.access = JwtAccessTokenService("k" * 48, "HS256", timedelta(minutes=15))
        self.refresh_gen = SecureRefreshTokenGenerator()
        self.config = AuthConfig(
            refresh_token_ttl_seconds=7 * 86400, session_max_lifetime_seconds=30 * 86400
        )

    def login(self, email: str, password: str = PASSWORD) -> SessionTokens:
        use_case = Login(
            self.uow, self.clock, self.hasher, self.access, self.refresh_gen, self.config
        )
        return use_case.execute(LoginCommand(email, password), CTX).tokens

    def refresh(self, token: str) -> SessionTokens:
        use_case = RefreshSession(self.uow, self.clock, self.access, self.refresh_gen, self.config)
        return use_case.execute(RefreshCommand(token), CTX)

    def authenticate(self, access_token: str) -> Actor:
        return AuthenticateAccessToken(self.uow, self.clock, self.access).execute(access_token)

    def create_admin(self, email: str = "admin@example.org") -> Actor:
        user = User.create(
            first_name="Root",
            last_name="Admin",
            email=email,
            password_hash=self.hasher.hash(PASSWORD),
            role=Role.ADMIN,
            now=self.clock.now(),
        )
        with self.uow() as uow:
            uow.users.add(user)
            uow.commit()
        return Actor(user.id, Role.ADMIN)

    def create_user(self, admin: Actor, email: str, role: Role = Role.MENTOR) -> User:
        command = CreateUserCommand("Luis", "Gómez", email, role, PASSWORD)
        return CreateUser(self.uow, self.clock, self.hasher).execute(admin, command, CTX)

    def audit_actions(self) -> list[AuditAction]:
        by_id = {v: k for k, v in AUDIT_ACTION_IDS.items()}
        with self.session_factory() as session:
            rows = session.scalars(select(AuditLogModel).order_by(AuditLogModel.id)).all()
        return [by_id[r.action_id] for r in rows]


@pytest.fixture
def stack(session_factory: sessionmaker[Session]) -> Stack:
    return Stack(session_factory)


def test_full_session_lifecycle(stack: Stack) -> None:
    admin = stack.create_admin()
    stack.create_user(admin, "luis@example.org")

    tokens = stack.login("luis@example.org")
    actor = stack.authenticate(tokens.access_token)
    assert actor.role is Role.MENTOR and actor.session_id is not None

    rotated = stack.refresh(tokens.refresh_token)
    assert rotated.refresh_token != tokens.refresh_token
    assert stack.authenticate(rotated.access_token).user_id == actor.user_id

    Logout(stack.uow, stack.clock).execute(stack.authenticate(rotated.access_token), CTX)
    with pytest.raises(Unauthorized):
        stack.authenticate(rotated.access_token)
    with pytest.raises(Unauthorized):
        stack.refresh(rotated.refresh_token)
    assert stack.audit_actions() == [
        AuditAction.USER_CREATED,
        AuditAction.LOGIN_SUCCEEDED,
        AuditAction.LOGOUT,
    ]


def test_only_hashes_reach_the_database(
    stack: Stack, session_factory: sessionmaker[Session]
) -> None:
    admin = stack.create_admin()
    stack.create_user(admin, "luis@example.org")
    tokens = stack.login("luis@example.org")
    with session_factory() as session:
        users = session.scalars(select(UserModel)).all()
        assert all(u.password_hash.startswith("$argon2id$") for u in users)
        assert all(PASSWORD not in u.password_hash for u in users)
        (stored,) = session.scalars(select(RefreshTokenModel)).all()
        assert stored.token_hash == stack.refresh_gen.hash(tokens.refresh_token)
        assert tokens.refresh_token not in stored.token_hash


def test_failed_logins_are_persisted_even_though_the_request_fails(stack: Stack) -> None:
    admin = stack.create_admin()
    stack.create_user(admin, "luis@example.org")
    for email, password in (("luis@example.org", "mala"), ("nadie@example.org", PASSWORD)):
        with pytest.raises(Unauthorized):
            stack.login(email, password)
    assert stack.audit_actions()[-2:] == [AuditAction.LOGIN_FAILED, AuditAction.LOGIN_FAILED]


def test_token_reuse_revokes_the_session_and_the_evidence_survives(stack: Stack) -> None:
    admin = stack.create_admin()
    stack.create_user(admin, "luis@example.org")
    first = stack.login("luis@example.org")
    second = stack.refresh(first.refresh_token)

    with pytest.raises(RefreshTokenReuse):
        stack.refresh(first.refresh_token)  # reutilizado

    with pytest.raises(Unauthorized):
        stack.refresh(second.refresh_token)
    with pytest.raises(Unauthorized):
        stack.authenticate(second.access_token)
    assert AuditAction.REFRESH_REUSE_DETECTED in stack.audit_actions()


def test_concurrent_refresh_with_the_same_token_only_one_wins(stack: Stack) -> None:
    """Dos pestañas refrescan a la vez: el lock de fila deja pasar una; la otra es un reuso."""
    admin = stack.create_admin()
    stack.create_user(admin, "luis@example.org")
    tokens = stack.login("luis@example.org")
    barrier = threading.Barrier(2)

    def attempt(_: int) -> object:
        barrier.wait()
        try:
            return stack.refresh(tokens.refresh_token)
        except (RefreshTokenReuse, Unauthorized) as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, range(2)))

    wins = [o for o in outcomes if isinstance(o, SessionTokens)]
    losses = [o for o in outcomes if isinstance(o, RefreshTokenReuse)]
    assert len(wins) == 1 and len(losses) == 1
    with pytest.raises(Unauthorized):  # la sesión quedó revocada: ni el ganador puede seguir
        stack.refresh(wins[0].refresh_token)


def test_deactivating_a_user_closes_their_sessions_immediately(stack: Stack) -> None:
    admin = stack.create_admin()
    user = stack.create_user(admin, "luis@example.org")
    tokens = stack.login("luis@example.org")

    SetUserActive(stack.uow, stack.clock).execute(admin, SetUserActiveCommand(user.id, False), CTX)

    with pytest.raises(Unauthorized):
        stack.authenticate(tokens.access_token)
    with pytest.raises(Unauthorized):
        stack.login("luis@example.org")
    with stack.session_factory() as session:  # soft delete: la fila y sus sesiones siguen ahí
        assert session.get(UserModel, user.id) is not None
        assert session.scalars(select(AuthSessionModel)).one().revoked_reason == "USER_DEACTIVATED"


def test_password_reset_and_change_close_the_right_sessions(stack: Stack) -> None:
    admin = stack.create_admin()
    user = stack.create_user(admin, "luis@example.org")
    phone, laptop = stack.login("luis@example.org"), stack.login("luis@example.org")
    laptop_actor = stack.authenticate(laptop.access_token)

    ChangeOwnPassword(stack.uow, stack.clock, stack.hasher).execute(
        laptop_actor, ChangePasswordCommand(PASSWORD, NEW_PASSWORD), CTX
    )
    stack.authenticate(laptop.access_token)  # la sesión actual sobrevive
    with pytest.raises(Unauthorized):
        stack.authenticate(phone.access_token)

    ResetPassword(stack.uow, stack.clock, stack.hasher).execute(
        admin, ResetPasswordCommand(user.id, "clave-temporal-9x"), CTX
    )
    with pytest.raises(Unauthorized):
        stack.authenticate(laptop.access_token)
    stack.login("luis@example.org", "clave-temporal-9x")


def test_duplicate_user_creation_rolls_back_the_audit_entry(stack: Stack) -> None:
    admin = stack.create_admin()
    stack.create_user(admin, "luis@example.org")
    before = stack.audit_actions()
    with pytest.raises(DuplicateEmail):
        stack.create_user(admin, "LUIS@example.org")
    assert stack.audit_actions() == before  # ni usuario ni auditoría a medias
