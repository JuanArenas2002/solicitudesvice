from collections.abc import Collection
from uuid import UUID

from app.application.commands.context import RequestContext
from app.application.ports.repositories.unit_of_work import UnitOfWorkFactory
from app.application.ports.services.clock import Clock
from app.application.use_cases.audit_helper import record_audit
from app.domain.enums.audit_action import AuditAction
from app.domain.enums.permission import Permission
from app.domain.enums.role import Role
from app.domain.exceptions.errors import InvalidValue, ProductTypeNotFound, UserNotFound
from app.domain.services.authorizer import require_permission
from app.domain.value_objects.actor import Actor


class GetUserProducts:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, actor: Actor, user_id: UUID) -> frozenset[int]:
        require_permission(actor, Permission.MANAGE_USERS)
        with self._uow_factory() as uow:
            if uow.users.get(user_id) is None:
                raise UserNotFound("Usuario no encontrado")
            return uow.assignments.product_ids(user_id)


class ListProductAssignments:
    """Qué productos revisa cada administrativo (para gestionarlos desde el listado)."""

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, actor: Actor) -> dict[UUID, frozenset[int]]:
        require_permission(actor, Permission.MANAGE_USERS)
        with self._uow_factory() as uow:
            return uow.assignments.all()


class SetUserProducts:
    """Define qué productos (formularios) revisa un administrativo. Solo el administrador."""

    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    def execute(
        self, actor: Actor, user_id: UUID, product_ids: Collection[int], ctx: RequestContext
    ) -> frozenset[int]:
        require_permission(actor, Permission.MANAGE_USERS)  # antes de tocar la BD
        wanted = frozenset(product_ids)
        now = self._clock.now()
        with self._uow_factory() as uow:
            user = uow.users.get(user_id)
            if user is None:
                raise UserNotFound("Usuario no encontrado")
            if user.role is not Role.ADMINISTRATIVO:
                raise InvalidValue(
                    "Solo el personal administrativo tiene productos asignados", field="user"
                )
            for product_id in wanted:
                if uow.product_types.get(product_id) is None:
                    raise ProductTypeNotFound(f"El producto {product_id} no existe")
            uow.assignments.replace(user_id, wanted)
            record_audit(
                uow,
                ctx,
                now,
                AuditAction.USER_PRODUCTS_ASSIGNED,
                actor_id=actor.user_id,
                entity_id=user_id,
                detail={"product_type_ids": [*sorted(wanted)]},
            )
            uow.commit()
            return wanted
