from app.application.commands.context import RequestContext
from app.application.ports.repositories.unit_of_work import UnitOfWorkFactory
from app.application.ports.services.clock import Clock
from app.application.use_cases.audit_helper import record_audit
from app.domain.enums.audit_action import AuditAction
from app.domain.exceptions.errors import Unauthorized
from app.domain.value_objects.actor import Actor


class Logout:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    def execute(self, actor: Actor, ctx: RequestContext) -> None:
        if actor.session_id is None:
            raise Unauthorized("Sesión inválida")
        now = self._clock.now()
        with self._uow_factory() as uow:
            session = uow.sessions.get_session(actor.session_id)
            if session is not None:
                session.revoke(now, "LOGOUT")
                uow.sessions.save_session(session)
            record_audit(
                uow,
                ctx,
                now,
                AuditAction.LOGOUT,
                actor_id=actor.user_id,
                entity_id=actor.session_id,
            )
            uow.commit()
