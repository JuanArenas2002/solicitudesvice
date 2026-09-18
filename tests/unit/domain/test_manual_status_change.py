from datetime import timedelta
from uuid import uuid4

import pytest

from app.domain.enums.request_status import RequestStatus as S
from app.domain.exceptions.errors import (
    Forbidden,
    InvalidStatusTransition,
    InvalidValue,
    RequestNotFound,
)
from app.domain.services.access_policy import RequestScope, ensure_can_view, scope_for
from app.domain.value_objects.actor import Actor
from tests.unit.domain.factories import ADMIN, MENTOR, NOW, STAFF, request_in

LATER = NOW + timedelta(hours=1)
NON_DRAFT = [s for s in S if s is not S.BORRADOR]


@pytest.mark.parametrize("source", NON_DRAFT)
@pytest.mark.parametrize("target", NON_DRAFT)
def test_staff_can_move_a_request_to_any_other_status(source: S, target: S) -> None:
    if source is target:
        pytest.skip("mismo estado")
    request = request_in(source)
    change = request.change_status(STAFF, LATER, target, "Ajuste por revisión externa")

    assert request.status is target
    assert (change.previous_status, change.new_status) == (source, target)
    assert change.reason == "Ajuste por revisión externa" and change.changed_by == STAFF.user_id
    # invariantes que la base de datos exige según el estado
    assert (request.reviewer_id is None) == (target is S.ENVIADA)
    if target in {S.CORRECCION_SOLICITADA, S.REENVIADA, S.APROBADA, S.RECHAZADA}:
        assert request.reviewed_at is not None
    assert (request.open_correction is not None) == (target is S.CORRECCION_SOLICITADA)


def test_the_reason_is_mandatory() -> None:
    request = request_in(S.APROBADA)
    for reason in (None, "", "   "):
        with pytest.raises(InvalidValue) as error:
            request.change_status(STAFF, LATER, S.EN_REVISION, reason)
        assert error.value.field == "reason"
    assert request.status is S.APROBADA


def test_drafts_are_private_and_cannot_be_targeted() -> None:
    with pytest.raises(InvalidStatusTransition):
        request_in(S.ENVIADA).change_status(STAFF, LATER, S.BORRADOR, "x")
    with pytest.raises(InvalidStatusTransition):
        request_in(S.BORRADOR).change_status(STAFF, LATER, S.ENVIADA, "x")


def test_the_same_status_is_rejected() -> None:
    with pytest.raises(InvalidStatusTransition):
        request_in(S.ENVIADA).change_status(STAFF, LATER, S.ENVIADA, "x")


@pytest.mark.parametrize("actor", [MENTOR, ADMIN])
def test_only_staff_can_change_the_status(actor: Actor) -> None:
    request = request_in(S.ENVIADA)
    with pytest.raises(Forbidden):
        request.change_status(actor, LATER, S.APROBADA, "x")
    assert request.status is S.ENVIADA


def test_a_correction_opened_by_hand_is_resolved_when_the_request_moves_on() -> None:
    request = request_in(S.EN_REVISION)
    request.change_status(STAFF, LATER, S.CORRECCION_SOLICITADA, "Falta la carta")
    (correction,) = request.corrections
    assert correction.is_open and correction.description == "Falta la carta"

    request.change_status(STAFF, LATER, S.APROBADA, "Se resolvió por otro medio")
    assert not correction.is_open and request.open_correction is None


def test_moving_to_correction_reuses_an_already_open_one() -> None:
    request = request_in(S.CORRECCION_SOLICITADA)
    request.change_status(STAFF, LATER, S.EN_REVISION, "Se reabre")
    request.change_status(STAFF, LATER, S.CORRECCION_SOLICITADA, "Otra vez")
    assert len([c for c in request.corrections if c.is_open]) == 1


# ---------------- alcance por productos asignados ----------------
def scoped(*product_ids: int) -> Actor:
    return Actor(uuid4(), STAFF.role, product_scope=frozenset(product_ids))


def test_staff_scope_is_limited_to_its_assigned_products() -> None:
    request = request_in(S.ENVIADA)  # producto 1
    ensure_can_view(scoped(1, 2), request)
    for actor in (scoped(2), scoped()):  # sin ese producto o sin ninguno
        with pytest.raises(RequestNotFound):
            ensure_can_view(actor, request)
    assert scope_for(scoped(3)) == RequestScope(None, False, frozenset({3}))
    ensure_can_view(STAFF, request)  # sin restricción explícita (admin y pruebas)
    ensure_can_view(ADMIN, request)
