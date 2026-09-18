"""Comandos de administración (no forman parte de la API).

    python -m app.cli create-admin --email admin@x.org --first-name Ana --last-name Perez
    python -m app.cli seed-forms

La contraseña del administrador se pide por consola (o variable ADMIN_PASSWORD, útil en Docker).
No existen credenciales por defecto.
"""

import argparse
import getpass
import os
import sys

from app.application.commands.context import RequestContext
from app.application.dto.page import PageRequest
from app.application.ports.repositories.unit_of_work import UnitOfWorkFactory
from app.application.queries.users import UserFilter
from app.application.use_cases.audit_helper import record_audit
from app.application.use_cases.forms.seed_default_forms import SeedDefaultForms
from app.config.settings import get_settings
from app.domain.entities.user import User
from app.domain.enums.audit_action import AuditAction
from app.domain.enums.role import Role
from app.domain.exceptions.errors import DomainError
from app.domain.value_objects.actor import Actor
from app.domain.value_objects.password import PlainPassword
from app.infrastructure.clock import SystemClock
from app.infrastructure.database.session import create_db_engine, create_session_factory
from app.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork
from app.infrastructure.security.passwords import Argon2PasswordHasher

CTX = RequestContext(correlation_id="cli")


def _uow_factory() -> UnitOfWorkFactory:
    factory = create_session_factory(create_db_engine(get_settings()))
    return lambda: SqlAlchemyUnitOfWork(factory)


def _password() -> str:
    from_env = os.environ.get("ADMIN_PASSWORD")
    if from_env:
        return from_env
    first = getpass.getpass("Contraseña: ")
    if first != getpass.getpass("Repita la contraseña: "):
        raise DomainError("Las contraseñas no coinciden")
    return first


MIN_WEAK_PASSWORD_LENGTH = 8


def _validated_password(allow_weak: bool) -> str:
    raw = _password()
    if not allow_weak:
        return PlainPassword(raw).value  # política completa (12 a 128 caracteres)
    if get_settings().environment == "production":
        raise DomainError("--allow-weak-password está prohibido en producción")
    if not MIN_WEAK_PASSWORD_LENGTH <= len(raw) <= 128:
        raise DomainError(
            f"La contraseña debe tener al menos {MIN_WEAK_PASSWORD_LENGTH} caracteres"
        )
    print(
        "AVISO: contraseña por debajo de la política (solo desarrollo). Cámbiela en cuanto pueda."
    )
    return raw


def create_admin(args: argparse.Namespace) -> None:
    password = _validated_password(args.allow_weak_password)
    clock = SystemClock()
    user = User.create(
        first_name=args.first_name,
        last_name=args.last_name,
        email=args.email,
        password_hash=Argon2PasswordHasher().hash(password),
        role=Role.ADMIN,
        now=clock.now(),
    )
    with _uow_factory()() as uow:
        uow.users.add(user)
        record_audit(
            uow,
            CTX,
            clock.now(),
            AuditAction.USER_CREATED,
            actor_id=None,
            entity_id=user.id,
            detail={"role": "ADMIN", "bootstrap": True},
        )
        uow.commit()
    print(f"Administrador creado: {user.email}")


def seed_forms(args: argparse.Namespace) -> None:
    uow_factory = _uow_factory()
    with uow_factory() as uow:
        admins = uow.users.list(UserFilter(role=Role.ADMIN, is_active=True), PageRequest(1, 1))
    if not admins.items:
        raise DomainError("No hay un administrador activo: ejecute primero create-admin")
    actor = Actor(user_id=admins.items[0].id, role=Role.ADMIN)
    loaded = SeedDefaultForms(uow_factory, SystemClock()).execute(actor, CTX)
    print("Formulario 'Artículo científico' cargado." if loaded else "Ya estaba cargado.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    admin = commands.add_parser("create-admin", help="Crea un usuario ADMIN")
    admin.add_argument("--email", required=True)
    admin.add_argument("--first-name", required=True)
    admin.add_argument("--last-name", required=True)
    admin.add_argument(
        "--allow-weak-password",
        action="store_true",
        help="Solo desarrollo: acepta 8+ caracteres en vez de la política de 12",
    )
    admin.set_defaults(handler=create_admin)
    commands.add_parser("seed-forms", help="Carga el formulario inicial de artículos").set_defaults(
        handler=seed_forms
    )
    args = parser.parse_args(argv)
    try:
        args.handler(args)
    except DomainError as error:
        print(f"Error: {error.message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
