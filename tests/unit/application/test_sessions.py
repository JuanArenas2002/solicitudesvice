import pytest

from app.application.commands.auth import RefreshCommand
from app.domain.enums.audit_action import AuditAction
from app.domain.enums.role import Role
from app.domain.exceptions.errors import RefreshTokenReuse, Unauthorized
from tests.unit.application.conftest import CTX, World


def refresh(world: World, token: str):
    return world.refresh_session().execute(RefreshCommand(token), CTX)


# ---------------- refresh: rotación y detección de reuso ----------------
def test_refresh_rotates_the_token(world: World) -> None:
    first = world.login_as(world.add_user()).tokens
    world.clock.advance(minutes=20)

    second = refresh(world, first.refresh_token)

    assert second.refresh_token != first.refresh_token
    assert second.access_token
    used = world.db.state.tokens[world.refresh.hash(first.refresh_token)]
    assert used.used_at == world.clock.now()  # el anterior quedó consumido
    assert len(world.db.state.tokens) == 2


def test_chain_of_refreshes_keeps_working(world: World) -> None:
    token = world.login_as(world.add_user()).tokens.refresh_token
    for _ in range(5):
        token = refresh(world, token).refresh_token


def test_reusing_a_consumed_token_revokes_the_whole_session(world: World) -> None:
    user = world.add_user()
    first = world.login_as(user).tokens
    second = refresh(world, first.refresh_token)

    with pytest.raises(RefreshTokenReuse):
        refresh(world, first.refresh_token)  # alguien reutiliza el token viejo

    (session,) = world.db.state.sessions.values()
    assert session.revoked_reason == "REFRESH_REUSE"  # persistido pese a la excepción
    (entry,) = world.audit_of(AuditAction.REFRESH_REUSE_DETECTED)
    assert entry.actor_id == user.id
    # El token legítimo más reciente también deja de servir: atacante y víctima pierden la sesión.
    with pytest.raises(Unauthorized):
        refresh(world, second.refresh_token)
    with pytest.raises(Unauthorized):
        world.authenticate().execute(second.access_token)


def test_unknown_refresh_token(world: World) -> None:
    with pytest.raises(Unauthorized):
        refresh(world, "inventado")


def test_expired_refresh_token(world: World) -> None:
    tokens = world.login_as(world.add_user()).tokens
    world.clock.advance(days=8)
    with pytest.raises(Unauthorized):
        refresh(world, tokens.refresh_token)


def test_session_has_an_absolute_lifetime(world: World) -> None:
    token = world.login_as(world.add_user()).tokens.refresh_token
    for _ in range(4):  # cada refresh renueva el token, pero la sesión no se extiende
        world.clock.advance(days=6)
        token = refresh(world, token).refresh_token
    world.clock.advance(days=6)  # día 30: el token aún vale (vence el 31) pero la sesión ya no
    with pytest.raises(Unauthorized):
        refresh(world, token)


def test_refresh_fails_for_deactivated_users_and_revoked_sessions(world: World) -> None:
    user = world.add_user()
    tokens = world.login_as(user).tokens
    world.db.state.users[user.id].is_active = False
    with pytest.raises(Unauthorized):
        refresh(world, tokens.refresh_token)
    # No se consume el token de una sesión inválida (no es un "reuso").
    assert world.db.state.tokens[world.refresh.hash(tokens.refresh_token)].used_at is None


# ---------------- authenticate ----------------
def test_authenticate_returns_actor_with_role_read_from_the_database(world: World) -> None:
    user = world.add_user(Role.MENTOR)
    tokens = world.login_as(user).tokens
    assert world.authenticate().execute(tokens.access_token).role is Role.MENTOR

    world.db.state.users[user.id].role = Role.ADMINISTRATIVO  # el cambio rige de inmediato
    actor = world.authenticate().execute(tokens.access_token)
    assert actor.role is Role.ADMINISTRATIVO and actor.user_id == user.id


@pytest.mark.parametrize("token", ["", "basura", "a|b", "1|2|3"])
def test_authenticate_rejects_malformed_tokens(world: World, token: str) -> None:
    with pytest.raises(Unauthorized):
        world.authenticate().execute(token)


def test_authenticate_rejects_deactivated_user_expired_session_and_foreign_session(
    world: World,
) -> None:
    user = world.add_user()
    other = world.add_user()
    tokens = world.login_as(user).tokens
    other_tokens = world.login_as(other).tokens

    # sesión de otro usuario con el token de este
    (session_id,) = [s.id for s in world.db.state.sessions.values() if s.user_id == other.id]
    with pytest.raises(Unauthorized):
        world.authenticate().execute(f"{user.id}|{session_id}")
    world.authenticate().execute(other_tokens.access_token)  # el legítimo sí

    world.clock.advance(days=31)
    with pytest.raises(Unauthorized):
        world.authenticate().execute(tokens.access_token)


def test_authenticate_rejects_deactivated_user(world: World) -> None:
    user = world.add_user()
    tokens = world.login_as(user).tokens
    world.db.state.users[user.id].is_active = False
    with pytest.raises(Unauthorized):
        world.authenticate().execute(tokens.access_token)


# ---------------- logout ----------------
def test_logout_revokes_the_session_immediately(world: World) -> None:
    user = world.add_user()
    tokens = world.login_as(user).tokens
    actor = world.authenticate().execute(tokens.access_token)

    world.logout().execute(actor, CTX)

    with pytest.raises(Unauthorized):
        world.authenticate().execute(tokens.access_token)
    with pytest.raises(Unauthorized):
        refresh(world, tokens.refresh_token)
    (entry,) = world.audit_of(AuditAction.LOGOUT)
    assert entry.actor_id == user.id and entry.entity_id == actor.session_id


def test_logout_only_closes_the_current_session(world: World) -> None:
    user = world.add_user()
    phone = world.login_as(user).tokens
    laptop = world.login_as(user).tokens
    world.logout().execute(world.authenticate().execute(phone.access_token), CTX)
    world.authenticate().execute(laptop.access_token)


def test_logout_requires_a_session(world: World) -> None:
    with pytest.raises(Unauthorized):
        world.logout().execute(world.actor_for(world.add_user()), CTX)
