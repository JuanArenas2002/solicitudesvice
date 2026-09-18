from app.application.commands.auth import ChangePasswordCommand
from app.application.commands.context import RequestContext
from app.application.ports.repositories.unit_of_work import UnitOfWorkFactory
from app.application.ports.services.clock import Clock
from app.application.ports.services.security import PasswordHasher
from app.application.use_cases.audit_helper import record_audit
from app.domain.enums.audit_action import AuditAction
from app.domain.exceptions.errors import Unauthorized, UserNotFound
from app.domain.value_objects.actor import Actor
from app.domain.value_objects.password import PlainPassword


class ChangeOwnPassword:
    def __init__(
        self, uow_factory: UnitOfWorkFactory, clock: Clock, hasher: PasswordHasher
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._hasher = hasher

    def execute(self, actor: Actor, command: ChangePasswordCommand, ctx: RequestContext) -> None:
        new_password = PlainPassword(command.new_password)  # política de contraseñas
        now = self._clock.now()
        with self._uow_factory() as uow:
            user = uow.users.get(actor.user_id)
            if user is None:
                raise UserNotFound("Usuario no encontrado")
            if not self._hasher.verify(user.password_hash, command.current_password):
                raise Unauthorized("La contraseña actual es incorrecta")
            user.set_password_hash(self._hasher.hash(new_password.value), now)
            uow.users.save(user)
            # Cerrar las demás sesiones: quien robó la clave anterior pierde el acceso.
            uow.sessions.revoke_all_for_user(
                user.id, now, "PASSWORD_CHANGED", except_session_id=actor.session_id
            )
            record_audit(
                uow, ctx, now, AuditAction.PASSWORD_CHANGED, actor_id=user.id, entity_id=user.id
            )
            uow.commit()
