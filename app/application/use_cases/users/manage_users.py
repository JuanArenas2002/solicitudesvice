from uuid import UUID

from app.application.commands.context import RequestContext
from app.application.commands.users import (
    CreateUserCommand,
    ResetPasswordCommand,
    SetUserActiveCommand,
    UpdateUserCommand,
)
from app.application.dto.page import Page, PageRequest
from app.application.ports.repositories.unit_of_work import UnitOfWork, UnitOfWorkFactory
from app.application.ports.services.clock import Clock
from app.application.ports.services.security import PasswordHasher
from app.application.queries.users import UserFilter
from app.application.use_cases.audit_helper import record_audit
from app.domain.entities.audit_entry import JsonValue
from app.domain.entities.user import User
from app.domain.enums.audit_action import AuditAction
from app.domain.enums.permission import Permission
from app.domain.exceptions.errors import UserNotFound
from app.domain.services.authorizer import require_permission
from app.domain.services.user_policy import ensure_can_manage_user
from app.domain.value_objects.actor import Actor
from app.domain.value_objects.password import PlainPassword


def _load(uow: UnitOfWork, user_id: UUID) -> User:
    user = uow.users.get(user_id)
    if user is None:
        raise UserNotFound("Usuario no encontrado")
    return user


class CreateUser:
    def __init__(
        self, uow_factory: UnitOfWorkFactory, clock: Clock, hasher: PasswordHasher
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._hasher = hasher

    def execute(self, actor: Actor, command: CreateUserCommand, ctx: RequestContext) -> User:
        require_permission(actor, Permission.MANAGE_USERS)
        password = PlainPassword(command.password)
        now = self._clock.now()
        user = User.create(
            first_name=command.first_name,
            last_name=command.last_name,
            email=command.email,
            password_hash=self._hasher.hash(password.value),
            role=command.role,
            now=now,
        )
        with self._uow_factory() as uow:
            uow.users.add(user)  # DuplicateEmail si el email ya existe
            record_audit(
                uow,
                ctx,
                now,
                AuditAction.USER_CREATED,
                actor_id=actor.user_id,
                entity_id=user.id,
                detail={"role": user.role.value},
            )
            uow.commit()
        return user


class UpdateUser:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    def execute(self, actor: Actor, command: UpdateUserCommand, ctx: RequestContext) -> User:
        require_permission(actor, Permission.MANAGE_USERS)  # antes de tocar la BD
        now = self._clock.now()
        with self._uow_factory() as uow:
            user = _load(uow, command.user_id)
            ensure_can_manage_user(actor, user, new_role=command.role)
            changed: list[JsonValue] = [
                name
                for name, value in (
                    ("first_name", command.first_name),
                    ("last_name", command.last_name),
                    ("email", command.email),
                    ("role", command.role),
                )
                if value is not None
            ]
            user.update_profile(
                now,
                first_name=command.first_name,
                last_name=command.last_name,
                email=command.email,
                role=command.role,
            )
            uow.users.save(user)
            record_audit(
                uow,
                ctx,
                now,
                AuditAction.USER_UPDATED,
                actor_id=actor.user_id,
                entity_id=user.id,
                detail={"changed": [*changed]},  # solo nombres de campos, nunca valores
            )
            uow.commit()
            return user


class SetUserActive:
    """Activar/desactivar (soft delete). Desactivar revoca todas las sesiones del usuario."""

    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    def execute(self, actor: Actor, command: SetUserActiveCommand, ctx: RequestContext) -> User:
        require_permission(actor, Permission.MANAGE_USERS)  # antes de tocar la BD
        now = self._clock.now()
        with self._uow_factory() as uow:
            user = _load(uow, command.user_id)
            ensure_can_manage_user(actor, user, new_active=command.active)
            if user.is_active == command.active:
                return user  # idempotente: sin cambios no hay auditoría
            user.set_active(command.active, now)
            uow.users.save(user)
            if not command.active:
                uow.sessions.revoke_all_for_user(user.id, now, "USER_DEACTIVATED")
            record_audit(
                uow,
                ctx,
                now,
                AuditAction.USER_ACTIVATED if command.active else AuditAction.USER_DEACTIVATED,
                actor_id=actor.user_id,
                entity_id=user.id,
            )
            uow.commit()
            return user


class ResetPassword:
    """El ADMIN asigna una clave temporal; se cierran todas las sesiones del usuario."""

    def __init__(
        self, uow_factory: UnitOfWorkFactory, clock: Clock, hasher: PasswordHasher
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._hasher = hasher

    def execute(self, actor: Actor, command: ResetPasswordCommand, ctx: RequestContext) -> None:
        require_permission(actor, Permission.MANAGE_USERS)
        password = PlainPassword(command.new_password)
        now = self._clock.now()
        with self._uow_factory() as uow:
            user = _load(uow, command.user_id)
            user.set_password_hash(self._hasher.hash(password.value), now)
            uow.users.save(user)
            uow.sessions.revoke_all_for_user(user.id, now, "PASSWORD_RESET")
            record_audit(
                uow,
                ctx,
                now,
                AuditAction.PASSWORD_RESET,
                actor_id=actor.user_id,
                entity_id=user.id,
            )
            uow.commit()


class GetUser:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, actor: Actor, user_id: UUID) -> User:
        require_permission(actor, Permission.MANAGE_USERS)
        with self._uow_factory() as uow:
            return _load(uow, user_id)


class GetCurrentUser:
    """Datos del propio usuario autenticado (cualquier rol)."""

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, actor: Actor) -> User:
        with self._uow_factory() as uow:
            return _load(uow, actor.user_id)


class ListUsers:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, actor: Actor, filters: UserFilter, page: PageRequest) -> Page[User]:
        require_permission(actor, Permission.MANAGE_USERS)
        with self._uow_factory() as uow:
            return uow.users.list(filters, page)
