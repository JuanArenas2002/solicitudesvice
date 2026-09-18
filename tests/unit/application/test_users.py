from uuid import uuid4

import pytest

from app.application.commands.auth import ChangePasswordCommand, LoginCommand
from app.application.commands.users import (
    CreateUserCommand,
    ResetPasswordCommand,
    SetUserActiveCommand,
    UpdateUserCommand,
)
from app.application.dto.page import MAX_PAGE_SIZE, PageRequest
from app.application.queries.users import UserFilter
from app.domain.enums.audit_action import AuditAction
from app.domain.enums.role import Role
from app.domain.exceptions.errors import (
    DuplicateEmail,
    Forbidden,
    InvalidValue,
    PasswordPolicyViolation,
    Unauthorized,
    UserNotFound,
)
from tests.unit.application.conftest import CTX, PASSWORD, World

NEW_PASSWORD = "otra-clave-segura-9"


def new_user_command(**overrides: object) -> CreateUserCommand:
    data: dict[str, object] = {
        "first_name": " Luis ",
        "last_name": "Gómez",
        "email": " LUIS@Example.org ",
        "role": Role.MENTOR,
        "password": "clave-inicial-123",
    }
    return CreateUserCommand(**{**data, **overrides})  # type: ignore[arg-type]


@pytest.fixture
def admin(world: World):
    return world.actor_for(world.add_user(Role.ADMIN))


# ---------------- crear ----------------
def test_admin_creates_a_user(world: World, admin) -> None:
    user = world.create_user().execute(admin, new_user_command(), CTX)

    stored = world.db.state.users[user.id]
    assert (stored.first_name, str(stored.email), stored.role) == (
        "Luis",
        "luis@example.org",
        Role.MENTOR,
    )
    assert stored.password_hash == world.hasher.hash("clave-inicial-123") and stored.is_active
    (entry,) = world.audit_of(AuditAction.USER_CREATED)
    assert entry.actor_id == admin.user_id and entry.entity_id == user.id
    assert entry.detail == {"role": "MENTOR"}  # sin contraseña ni datos personales


@pytest.mark.parametrize("role", [Role.MENTOR, Role.ADMINISTRATIVO])
def test_only_admins_manage_users(world: World, role: Role) -> None:
    actor = world.actor_for(world.add_user(role))
    target = world.add_user()
    users_before = len(world.db.state.users)

    with pytest.raises(Forbidden):
        world.create_user().execute(actor, new_user_command(), CTX)
    with pytest.raises(Forbidden):
        world.update_user().execute(actor, UpdateUserCommand(target.id, first_name="X"), CTX)
    with pytest.raises(Forbidden):
        world.update_user().execute(actor, UpdateUserCommand(uuid4(), first_name="X"), CTX)
    with pytest.raises(Forbidden):
        world.set_active().execute(actor, SetUserActiveCommand(target.id, False), CTX)
    with pytest.raises(Forbidden):
        world.reset_password().execute(actor, ResetPasswordCommand(target.id, NEW_PASSWORD), CTX)
    with pytest.raises(Forbidden):
        world.get_user().execute(actor, target.id)
    with pytest.raises(Forbidden):
        world.list_users().execute(actor, UserFilter(), PageRequest())

    assert len(world.db.state.users) == users_before and world.db.state.audit == []
    assert world.db.state.users[target.id].is_active


def test_duplicate_email_is_a_conflict_and_leaves_no_trace(world: World, admin) -> None:
    world.add_user(email="luis@example.org")
    before = len(world.db.state.users)
    with pytest.raises(DuplicateEmail):
        world.create_user().execute(
            admin, new_user_command(), CTX
        )  # mismo email, otra capitalización
    assert len(world.db.state.users) == before
    assert world.audit_of(AuditAction.USER_CREATED) == []


def test_password_policy_is_enforced_on_creation(world: World, admin) -> None:
    with pytest.raises(PasswordPolicyViolation):
        world.create_user().execute(admin, new_user_command(password="corta"), CTX)
    assert len(world.db.state.users) == 1  # solo el admin


def test_invalid_data_is_rejected_before_persisting(world: World, admin) -> None:
    with pytest.raises(InvalidValue):
        world.create_user().execute(admin, new_user_command(email="no-es-email"), CTX)
    with pytest.raises(InvalidValue):
        world.create_user().execute(admin, new_user_command(first_name="  "), CTX)


# ---------------- actualizar ----------------
def test_update_changes_only_given_fields_and_audits_field_names(world: World, admin) -> None:
    target = world.add_user(first_name="Ana", last_name="Pérez", email="ana@example.org")
    updated = world.update_user().execute(
        admin, UpdateUserCommand(target.id, first_name="Ana María", role=Role.ADMINISTRATIVO), CTX
    )
    assert (updated.first_name, updated.last_name, updated.role) == (
        "Ana María",
        "Pérez",
        Role.ADMINISTRATIVO,
    )
    (entry,) = world.audit_of(AuditAction.USER_UPDATED)
    assert entry.detail == {"changed": ["first_name", "role"]}


def test_update_unknown_user_and_duplicate_email(world: World, admin) -> None:
    other = world.add_user(email="otro@example.org")
    target = world.add_user(email="ana@example.org")
    with pytest.raises(UserNotFound):
        world.update_user().execute(admin, UpdateUserCommand(uuid4(), first_name="X"), CTX)
    with pytest.raises(DuplicateEmail):
        world.update_user().execute(
            admin, UpdateUserCommand(target.id, email=other.email.value), CTX
        )
    assert str(world.db.state.users[target.id].email) == "ana@example.org"


def test_admin_cannot_lock_themselves_out(world: World, admin) -> None:
    with pytest.raises(Forbidden):
        world.update_user().execute(admin, UpdateUserCommand(admin.user_id, role=Role.MENTOR), CTX)
    with pytest.raises(Forbidden):
        world.set_active().execute(admin, SetUserActiveCommand(admin.user_id, False), CTX)
    # sí puede editar sus propios datos y mantener su rol
    world.update_user().execute(
        admin, UpdateUserCommand(admin.user_id, first_name="Root", role=Role.ADMIN), CTX
    )
    assert world.db.state.users[admin.user_id].first_name == "Root"


# ---------------- activar / desactivar ----------------
def test_deactivation_revokes_every_session_and_blocks_login(world: World, admin) -> None:
    target = world.add_user(email="ana@example.org")
    phone, laptop = world.login_as(target).tokens, world.login_as(target).tokens

    world.set_active().execute(admin, SetUserActiveCommand(target.id, False), CTX)

    assert not world.db.state.users[target.id].is_active  # soft delete: la fila sigue existiendo
    for tokens in (phone, laptop):
        with pytest.raises(Unauthorized):
            world.authenticate().execute(tokens.access_token)
    with pytest.raises(Unauthorized):
        world.login().execute(LoginCommand("ana@example.org", PASSWORD), CTX)
    assert len(world.audit_of(AuditAction.USER_DEACTIVATED)) == 1


def test_activation_is_idempotent_and_restores_access(world: World, admin) -> None:
    target = world.add_user(email="ana@example.org", active=False)
    world.set_active().execute(admin, SetUserActiveCommand(target.id, True), CTX)
    world.set_active().execute(admin, SetUserActiveCommand(target.id, True), CTX)  # sin cambios
    assert len(world.audit_of(AuditAction.USER_ACTIVATED)) == 1
    world.login().execute(LoginCommand("ana@example.org", PASSWORD), CTX)


# ---------------- contraseñas ----------------
def test_reset_password_replaces_it_and_closes_all_sessions(world: World, admin) -> None:
    target = world.add_user(email="ana@example.org")
    tokens = world.login_as(target).tokens

    world.reset_password().execute(admin, ResetPasswordCommand(target.id, NEW_PASSWORD), CTX)

    with pytest.raises(Unauthorized):
        world.authenticate().execute(tokens.access_token)
    with pytest.raises(Unauthorized):
        world.login().execute(LoginCommand("ana@example.org", PASSWORD), CTX)
    world.login().execute(LoginCommand("ana@example.org", NEW_PASSWORD), CTX)
    (entry,) = world.audit_of(AuditAction.PASSWORD_RESET)
    assert NEW_PASSWORD not in str(entry) and entry.entity_id == target.id


def test_reset_password_validates_policy_and_target(world: World, admin) -> None:
    target = world.add_user()
    with pytest.raises(PasswordPolicyViolation):
        world.reset_password().execute(admin, ResetPasswordCommand(target.id, "corta"), CTX)
    with pytest.raises(UserNotFound):
        world.reset_password().execute(admin, ResetPasswordCommand(uuid4(), NEW_PASSWORD), CTX)


def test_change_own_password_keeps_current_session_and_closes_the_others(world: World) -> None:
    user = world.add_user(email="ana@example.org")
    phone = world.login_as(user).tokens
    laptop = world.login_as(user).tokens
    actor = world.authenticate().execute(laptop.access_token)

    world.change_password().execute(actor, ChangePasswordCommand(PASSWORD, NEW_PASSWORD), CTX)

    world.authenticate().execute(laptop.access_token)  # la sesión actual sigue viva
    with pytest.raises(Unauthorized):
        world.authenticate().execute(phone.access_token)  # las demás se cierran
    world.login().execute(LoginCommand("ana@example.org", NEW_PASSWORD), CTX)
    assert len(world.audit_of(AuditAction.PASSWORD_CHANGED)) == 1


def test_change_own_password_requires_the_current_one_and_a_strong_new_one(world: World) -> None:
    user = world.add_user()
    actor = world.authenticate().execute(world.login_as(user).tokens.access_token)
    with pytest.raises(Unauthorized):
        world.change_password().execute(
            actor, ChangePasswordCommand("equivocada", NEW_PASSWORD), CTX
        )
    with pytest.raises(PasswordPolicyViolation):
        world.change_password().execute(actor, ChangePasswordCommand(PASSWORD, "corta"), CTX)
    assert world.db.state.users[user.id].password_hash == world.hasher.hash(PASSWORD)


# ---------------- consultas ----------------
def test_get_user_and_get_me(world: World, admin) -> None:
    target = world.add_user()
    assert world.get_user().execute(admin, target.id).id == target.id
    with pytest.raises(UserNotFound):
        world.get_user().execute(admin, uuid4())
    me = world.get_me().execute(world.actor_for(target))
    assert me.id == target.id  # cualquier rol puede ver su propio perfil


def test_list_users_filters_orders_and_paginates(world: World, admin) -> None:
    for i in range(25):
        world.add_user(
            Role.MENTOR, first_name=f"Mentor{i:02d}", last_name="Zeta", email=f"m{i}@example.org"
        )
    world.add_user(
        Role.ADMINISTRATIVO, first_name="Carla", last_name="Alfa", email="carla@example.org"
    )
    world.add_user(
        Role.MENTOR, first_name="Off", last_name="Zeta", email="off@example.org", active=False
    )

    first = world.list_users().execute(
        admin, UserFilter(role=Role.MENTOR, is_active=True), PageRequest(1, 10)
    )
    assert (first.total, first.total_pages, len(first.items)) == (25, 3, 10)
    last = world.list_users().execute(
        admin, UserFilter(role=Role.MENTOR, is_active=True), PageRequest(3, 10)
    )
    assert len(last.items) == 5
    everyone = world.list_users().execute(admin, UserFilter(), PageRequest(1, 100))
    assert everyone.items[0].last_name == "Alfa"  # orden por apellido
    found = world.list_users().execute(admin, UserFilter(search="carla@EXAMPLE"), PageRequest())
    assert [u.first_name for u in found.items] == ["Carla"]


@pytest.mark.parametrize(("page", "size"), [(0, 20), (1, 0), (1, MAX_PAGE_SIZE + 1), (-1, 5)])
def test_pagination_limits(page: int, size: int) -> None:
    with pytest.raises(InvalidValue):
        PageRequest(page, size)
    PageRequest(1, MAX_PAGE_SIZE)
