from app.domain.entities.user import User
from app.domain.enums.permission import Permission
from app.domain.enums.role import Role
from app.domain.exceptions.errors import Forbidden
from app.domain.services.authorizer import require_permission
from app.domain.value_objects.actor import Actor


def ensure_can_manage_user(
    actor: Actor,
    target: User,
    *,
    new_role: Role | None = None,
    new_active: bool | None = None,
) -> None:
    """Un ADMIN gestiona usuarios, pero no puede bloquearse a sí mismo.

    Como el actor es un ADMIN activo y no puede degradarse ni desactivarse, siempre queda al menos
    un ADMIN activo: no hace falta una regla aparte de "último administrador".
    """
    require_permission(actor, Permission.MANAGE_USERS)
    if actor.user_id == target.id:
        if new_active is False:
            raise Forbidden("No puede desactivar su propia cuenta")
        if new_role is not None and new_role is not target.role:
            raise Forbidden("No puede cambiar su propio rol")
