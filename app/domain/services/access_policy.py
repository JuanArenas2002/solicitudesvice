from dataclasses import dataclass
from uuid import UUID

from app.domain.entities.research_product_request import ResearchProductRequest
from app.domain.enums.permission import Permission
from app.domain.enums.request_status import RequestStatus
from app.domain.exceptions.errors import Forbidden, RequestNotFound
from app.domain.services.authorizer import has_permission
from app.domain.value_objects.actor import Actor


@dataclass(frozen=True, slots=True)
class RequestScope:
    """Qué solicitudes puede ver un actor. Los repositorios lo aplican en la consulta."""

    mentor_id: UUID | None  # None = de cualquier mentor
    include_drafts: bool
    product_ids: frozenset[int] | None = None  # None = de cualquier producto


def scope_for(actor: Actor) -> RequestScope:
    if has_permission(actor.role, Permission.VIEW_REQUESTS):
        # los borradores son privados; un administrativo solo ve los productos que tiene asignados
        return RequestScope(mentor_id=None, include_drafts=False, product_ids=actor.product_scope)
    if has_permission(actor.role, Permission.VIEW_OWN_REQUESTS):
        return RequestScope(mentor_id=actor.user_id, include_drafts=True)
    raise Forbidden("No tiene permiso para consultar solicitudes")


def ensure_can_view(actor: Actor, request: ResearchProductRequest) -> None:
    """Falla con RequestNotFound (no Forbidden) para no revelar que la solicitud existe (IDOR)."""
    scope = scope_for(actor)
    owner_ok = scope.mentor_id is None or request.mentor_id == scope.mentor_id
    draft_ok = scope.include_drafts or request.status is not RequestStatus.BORRADOR
    product_ok = scope.product_ids is None or request.product_type_id in scope.product_ids
    if not (owner_ok and draft_ok and product_ok):
        raise RequestNotFound("Solicitud no encontrada")


def ensure_can_view_history(actor: Actor, request: ResearchProductRequest) -> None:
    ensure_can_view(actor, request)
    is_owner = request.mentor_id == actor.user_id
    if not is_owner and not has_permission(actor.role, Permission.VIEW_REQUEST_HISTORY):
        raise Forbidden("No tiene permiso para consultar el historial")
