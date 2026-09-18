import pytest

from app.domain.enums.permission import Permission as P
from app.domain.enums.request_status import RequestStatus as S
from app.domain.enums.role import Role
from app.domain.exceptions.errors import Forbidden, RequestNotFound
from app.domain.services.access_policy import (
    RequestScope,
    ensure_can_view,
    ensure_can_view_history,
    scope_for,
)
from app.domain.services.authorizer import ROLE_PERMISSIONS, has_permission, require_permission
from tests.unit.domain.factories import ADMIN, MENTOR, OTHER_MENTOR, STAFF, request_in

MATRIX = {
    P.MANAGE_USERS: {Role.ADMIN},
    P.CREATE_REQUEST: {Role.MENTOR},
    P.EDIT_OWN_REQUEST: {Role.MENTOR},
    P.SUBMIT_OWN_REQUEST: {Role.MENTOR},
    P.VIEW_OWN_REQUESTS: {Role.MENTOR},
    P.MANAGE_OWN_ATTACHMENTS: {Role.MENTOR},
    P.VIEW_REQUESTS: {Role.ADMIN, Role.ADMINISTRATIVO},
    P.VIEW_REQUEST_HISTORY: {Role.ADMIN, Role.ADMINISTRATIVO},
    P.DOWNLOAD_ATTACHMENTS: {Role.ADMINISTRATIVO},
    P.REVIEW_REQUEST: {Role.ADMINISTRATIVO},
    P.REQUEST_CORRECTION: {Role.ADMINISTRATIVO},
    P.APPROVE_REQUEST: {Role.ADMINISTRATIVO},
    P.REJECT_REQUEST: {Role.ADMINISTRATIVO},
    P.CHANGE_REQUEST_STATUS: {Role.ADMINISTRATIVO},
    P.MANAGE_FORMS: {Role.ADMIN, Role.ADMINISTRATIVO},
    P.VIEW_FORMS: {Role.ADMIN, Role.ADMINISTRATIVO, Role.MENTOR},
    P.VIEW_AUDIT: {Role.ADMIN, Role.ADMINISTRATIVO},
    P.VIEW_SECURITY_AUDIT: {Role.ADMIN},
}


def test_matrix_covers_every_permission() -> None:
    assert set(MATRIX) == set(P)


@pytest.mark.parametrize("permission", list(P))
@pytest.mark.parametrize("role", list(Role))
def test_permission_matrix(role: Role, permission: P) -> None:
    assert has_permission(role, permission) is (role in MATRIX[permission])


def test_admin_has_no_workflow_or_editing_power() -> None:
    forbidden = {
        P.CREATE_REQUEST,
        P.EDIT_OWN_REQUEST,
        P.SUBMIT_OWN_REQUEST,
        P.REVIEW_REQUEST,
        P.REQUEST_CORRECTION,
        P.APPROVE_REQUEST,
        P.REJECT_REQUEST,
        P.CHANGE_REQUEST_STATUS,
        P.DOWNLOAD_ATTACHMENTS,
    }
    assert not (ROLE_PERMISSIONS[Role.ADMIN] & forbidden)


def test_require_permission_raises_forbidden() -> None:
    require_permission(ADMIN, P.MANAGE_USERS)
    with pytest.raises(Forbidden):
        require_permission(STAFF, P.MANAGE_USERS)
    with pytest.raises(Forbidden):
        require_permission(MENTOR, P.APPROVE_REQUEST)


def test_scopes() -> None:
    assert scope_for(MENTOR) == RequestScope(mentor_id=MENTOR.user_id, include_drafts=True)
    assert scope_for(STAFF) == RequestScope(mentor_id=None, include_drafts=False)
    assert scope_for(ADMIN) == RequestScope(mentor_id=None, include_drafts=False)


def test_owner_sees_own_request_including_draft() -> None:
    ensure_can_view(MENTOR, request_in(S.BORRADOR))
    ensure_can_view_history(MENTOR, request_in(S.EN_REVISION))


@pytest.mark.parametrize("status", list(S))
def test_horizontal_escalation_is_blocked_with_not_found(status: S) -> None:
    """IDOR: un mentor no puede ver la solicitud de otro, y no debe saber que existe."""
    request = request_in(status)
    with pytest.raises(RequestNotFound):
        ensure_can_view(OTHER_MENTOR, request)
    with pytest.raises(RequestNotFound):
        ensure_can_view_history(OTHER_MENTOR, request)


@pytest.mark.parametrize("actor", [STAFF, ADMIN])
def test_drafts_are_private_to_their_mentor(actor) -> None:
    with pytest.raises(RequestNotFound):
        ensure_can_view(actor, request_in(S.BORRADOR))


@pytest.mark.parametrize("actor", [STAFF, ADMIN])
@pytest.mark.parametrize("status", [s for s in S if s is not S.BORRADOR])
def test_staff_and_admin_read_submitted_requests_and_history(actor, status: S) -> None:
    request = request_in(status)
    ensure_can_view(actor, request)
    ensure_can_view_history(actor, request)
