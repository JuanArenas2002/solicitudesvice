from uuid import uuid4

import pytest

from app.application.dto.page import PageRequest
from app.domain.enums.request_status import RequestStatus as S
from app.domain.enums.role import Role
from tests.unit.application.conftest import CTX, World
from tests.unit.application.test_requests import Cast

PAGE = PageRequest(1, 50)


@pytest.fixture
def cast(world: World) -> Cast:
    return Cast(world)


def inbox(world: World, cast: Cast, unread_only: bool = False):
    return world.list_notifications().execute(cast.mentor, unread_only, PAGE)


def test_nothing_is_notified_for_what_the_mentor_does_himself(world: World, cast: Cast) -> None:
    cast.in_status(S.ENVIADA)  # el mentor creó, llenó y envió
    assert inbox(world, cast).page.total == 0 and inbox(world, cast).unread == 0


def test_every_staff_action_notifies_the_owner(world: World, cast: Cast) -> None:
    rid = cast.in_status(S.ENVIADA).request.id
    world.start_review().execute(cast.staff, rid, CTX)
    world.request_correction().execute(cast.staff, rid, "Falta el DOI", CTX)
    world.resubmit().execute(cast.mentor, rid, CTX)  # lo hace el mentor: no avisa
    world.start_review().execute(cast.staff, rid, CTX)
    world.approve().execute(cast.staff, rid, "Todo en orden", CTX)
    world.change_status().execute(cast.staff, rid, S.EN_REVISION, "Se reabre", CTX)

    result = inbox(world, cast)
    assert [(n.status, n.reason) for n in result.page.items] == [  # la más reciente primero
        (S.EN_REVISION, "Se reabre"),
        (S.APROBADA, "Todo en orden"),
        (S.EN_REVISION, None),
        (S.CORRECCION_SOLICITADA, "Falta el DOI"),
        (S.EN_REVISION, None),
    ]
    assert result.unread == 5 and all(n.request_id == rid for n in result.page.items)
    assert result.page.items[0].request_number.startswith("SOL-")


def test_only_the_owner_is_notified_and_never_the_staff_member(world: World, cast: Cast) -> None:
    rid = cast.in_status(S.ENVIADA).request.id
    world.start_review().execute(cast.staff, rid, CTX)
    for actor in (cast.staff, cast.other, cast.admin):
        assert world.list_notifications().execute(actor, False, PAGE).page.total == 0
        assert world.count_unread().execute(actor) == 0
    assert world.count_unread().execute(cast.mentor) == 1


def test_a_failed_transition_leaves_no_notification(world: World, cast: Cast) -> None:
    rid = cast.in_status(S.ENVIADA).request.id
    with pytest.raises(Exception):  # noqa: B017,PT011 - aprobar sin revisar es inválido
        world.approve().execute(cast.staff, rid, None, CTX)
    assert inbox(world, cast).page.total == 0


def test_mark_read_is_personal_and_idempotent(world: World, cast: Cast) -> None:
    rid = cast.in_status(S.ENVIADA).request.id
    world.start_review().execute(cast.staff, rid, CTX)
    world.approve().execute(cast.staff, rid, None, CTX)
    first, second = inbox(world, cast).page.items

    assert world.mark_read().execute(cast.other, [first.id]) == 0  # ajena: se ignora
    assert world.count_unread().execute(cast.mentor) == 2
    assert world.mark_read().execute(cast.mentor, [first.id, uuid4()]) == 1
    assert world.mark_read().execute(cast.mentor, [first.id]) == 0  # ya estaba leída
    assert world.count_unread().execute(cast.mentor) == 1
    assert [n.id for n in inbox(world, cast, unread_only=True).page.items] == [second.id]

    assert world.mark_read().execute(cast.mentor, None) == 1  # todas
    assert world.count_unread().execute(cast.mentor) == 0
    assert inbox(world, cast).page.total == 2  # siguen en el historial de avisos


def test_pagination_of_notifications(world: World, cast: Cast) -> None:
    rid = cast.in_status(S.ENVIADA).request.id
    for i in range(3):
        target = S.EN_REVISION if i % 2 == 0 else S.ENVIADA
        world.change_status().execute(cast.staff, rid, target, f"cambio {i}", CTX)
    result = world.list_notifications().execute(cast.mentor, False, PageRequest(1, 2))
    assert (len(result.page.items), result.page.total, result.unread) == (2, 3, 3)


def test_assignments_listing_is_admin_only(world: World, cast: Cast) -> None:
    from app.domain.exceptions.errors import Forbidden

    staff_user = world.add_user(Role.ADMINISTRATIVO)
    world.set_user_products().execute(cast.admin, staff_user.id, [cast.product_id], CTX)
    assert world.list_assignments().execute(cast.admin) == {staff_user.id: {cast.product_id}}
    for outsider in (cast.staff, cast.mentor):
        with pytest.raises(Forbidden):
            world.list_assignments().execute(outsider)
