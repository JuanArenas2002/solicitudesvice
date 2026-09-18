import pytest

from app.application.commands.auth import LoginCommand
from app.domain.enums.audit_action import AuditAction
from app.domain.exceptions.errors import Unauthorized
from tests.unit.application.conftest import CTX, PASSWORD, World


def test_successful_login_creates_session_tokens_and_audit(world: World) -> None:
    user = world.add_user(email="ana@example.org")
    result = world.login_as(user)

    assert result.user.id == user.id and result.user.last_login_at == world.clock.now()
    tokens = result.tokens
    assert tokens.access_token and tokens.refresh_token
    (session,) = world.db.state.sessions.values()
    assert session.user_id == user.id and session.is_active(world.clock.now())

    # Solo se guarda el HASH del refresh token, nunca el valor entregado al cliente.
    (stored,) = world.db.state.tokens.values()
    assert tokens.refresh_token not in world.db.state.tokens
    assert stored.token_hash == world.refresh.hash(tokens.refresh_token)

    (entry,) = world.audit_of(AuditAction.LOGIN_SUCCEEDED)
    assert entry.actor_id == user.id and entry.entity_id == session.id
    assert entry.correlation_id == CTX.correlation_id and entry.ip_address == CTX.ip_address


def test_email_is_case_insensitive(world: World) -> None:
    world.add_user(email="ana@example.org")
    world.login().execute(LoginCommand("  ANA@Example.ORG ", PASSWORD), CTX)


@pytest.mark.parametrize(
    ("email", "password", "reason", "active"),
    [
        ("ana@example.org", "clave-equivocada", "bad_password", True),
        ("nadie@example.org", PASSWORD, "unknown_user", True),
        ("no-es-un-email", PASSWORD, "unknown_user", True),
        ("ana@example.org", PASSWORD, "inactive_user", False),
    ],
)
def test_failed_login_is_audited_and_never_reveals_why(
    world: World, email: str, password: str, reason: str, active: bool
) -> None:
    world.add_user(email="ana@example.org", active=active)

    with pytest.raises(Unauthorized) as error:
        world.login().execute(LoginCommand(email, password), CTX)

    assert error.value.message == "Credenciales inválidas"  # idéntico en todos los casos
    assert world.db.state.sessions == {} and world.db.state.tokens == {}
    (entry,) = world.audit_of(AuditAction.LOGIN_FAILED)  # se confirmó pese a la excepción
    assert entry.detail == {"reason": reason}
    assert password not in str(entry.detail) and "password" not in entry.detail


def test_unknown_user_still_spends_hashing_time(world: World) -> None:
    with pytest.raises(Unauthorized):
        world.login().execute(LoginCommand("nadie@example.org", PASSWORD), CTX)
    assert world.hasher.dummy_calls == 1


def test_known_user_does_not_use_the_dummy_hash(world: World) -> None:
    user = world.add_user()
    world.login_as(user)
    assert world.hasher.dummy_calls == 0


def test_password_is_rehashed_when_parameters_are_outdated(world: World) -> None:
    user = world.add_user()
    world.hasher.rehash_needed = True
    world.login_as(user)
    assert world.db.state.users[user.id].password_hash == world.hasher.hash(PASSWORD)


def test_refresh_token_never_outlives_the_session() -> None:
    from app.application.dto.auth import AuthConfig

    world = World()
    world.config = AuthConfig(
        refresh_token_ttl_seconds=10 * 86400, session_max_lifetime_seconds=86400
    )
    result = world.login_as(world.add_user())
    (session,) = world.db.state.sessions.values()
    assert result.tokens.refresh_expires_at == session.expires_at
