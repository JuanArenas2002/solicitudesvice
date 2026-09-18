from collections.abc import Mapping
from types import MappingProxyType

from app.domain.enums.permission import Permission as P
from app.domain.enums.role import Role
from app.domain.exceptions.errors import Forbidden
from app.domain.value_objects.actor import Actor

# Única fuente de verdad de permisos. Migrar a RBAC + permisos en BD = cambiar el origen de este
# mapa; los casos de uso y el dominio solo llaman a has_permission / require_permission.
ROLE_PERMISSIONS: Mapping[Role, frozenset[P]] = MappingProxyType(
    {
        Role.ADMIN: frozenset(
            {
                P.MANAGE_USERS,
                P.MANAGE_FORMS,
                P.VIEW_FORMS,
                # Solo lectura para soporte: ninguna acción de workflow.
                P.VIEW_REQUESTS,
                P.VIEW_REQUEST_HISTORY,
                P.VIEW_AUDIT,
                P.VIEW_SECURITY_AUDIT,
            }
        ),
        Role.ADMINISTRATIVO: frozenset(
            {
                P.VIEW_REQUESTS,
                P.VIEW_REQUEST_HISTORY,
                P.DOWNLOAD_ATTACHMENTS,
                P.REVIEW_REQUEST,
                P.REQUEST_CORRECTION,
                P.APPROVE_REQUEST,
                P.REJECT_REQUEST,
                P.CHANGE_REQUEST_STATUS,
                P.VIEW_AUDIT,
                P.MANAGE_FORMS,
                P.VIEW_FORMS,
            }
        ),
        Role.MENTOR: frozenset(
            {
                P.CREATE_REQUEST,
                P.EDIT_OWN_REQUEST,
                P.SUBMIT_OWN_REQUEST,
                P.VIEW_OWN_REQUESTS,
                P.MANAGE_OWN_ATTACHMENTS,
                P.VIEW_FORMS,
            }
        ),
    }
)


def has_permission(role: Role, permission: P) -> bool:
    return permission in ROLE_PERMISSIONS[role]


def require_permission(actor: Actor, permission: P) -> None:
    if not has_permission(actor.role, permission):
        raise Forbidden(f"No tiene permiso para esta operación ({permission})")
