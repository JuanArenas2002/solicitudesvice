import pytest

from app.domain.enums.request_action import RequestAction as A
from app.domain.enums.request_status import RequestStatus as S
from app.domain.exceptions.errors import (
    ConcurrentModification,
    Forbidden,
    IncompleteProduct,
    InvalidRequestState,
    InvalidStatusTransition,
    InvalidValue,
)
from app.domain.forms.filled_form import FilledForm
from app.domain.services.request_workflow import EDITABLE_STATUSES, TRANSITIONS
from tests.unit.domain.factories import (
    ADMIN,
    FORM,
    MENTOR,
    NOW,
    OTHER_MENTOR,
    OTHER_STAFF,
    STAFF,
    complete_form,
    new_draft,
    request_in,
)

PERFORMERS = {
    A.SUBMIT: MENTOR,
    A.RESUBMIT: MENTOR,
    A.START_REVIEW: STAFF,
    A.REQUEST_CORRECTION: STAFF,
    A.APPROVE: STAFF,
    A.REJECT: STAFF,
}


def perform(request, action, actor=None):
    actor = actor or PERFORMERS[action]
    article = complete_form(request.id)
    match action:
        case A.SUBMIT:
            return request.submit(actor, NOW, article)
        case A.RESUBMIT:
            return request.resubmit(actor, NOW, article)
        case A.START_REVIEW:
            return request.start_review(actor, NOW)
        case A.REQUEST_CORRECTION:
            return request.request_correction(actor, NOW, "Corregir el DOI")
        case A.APPROVE:
            return request.approve(actor, NOW)
        case A.REJECT:
            return request.reject(actor, NOW, "No aplica")


@pytest.mark.parametrize("action", list(A))
@pytest.mark.parametrize("status", list(S))
def test_every_transition_is_valid_or_rejected(status: S, action: A) -> None:
    """Matriz completa estado × acción: solo las transiciones de la tabla son posibles."""
    request = request_in(status)
    rule = TRANSITIONS[action]
    if status in rule.sources:
        change = perform(request, action)
        assert request.status is rule.target
        assert (change.previous_status, change.new_status) == (status, rule.target)
    else:
        with pytest.raises(InvalidStatusTransition):
            perform(request, action)
        assert request.status is status  # sin mutación parcial


def test_workflow_table_matches_the_documented_state_machine() -> None:
    edges = {(s, r.target) for r in TRANSITIONS.values() for s in r.sources}
    assert edges == {
        (S.BORRADOR, S.ENVIADA),
        (S.ENVIADA, S.EN_REVISION),
        (S.REENVIADA, S.EN_REVISION),
        (S.EN_REVISION, S.CORRECCION_SOLICITADA),
        (S.CORRECCION_SOLICITADA, S.REENVIADA),
        (S.EN_REVISION, S.APROBADA),
        (S.EN_REVISION, S.RECHAZADA),
    }


@pytest.mark.parametrize("terminal", [S.APROBADA, S.RECHAZADA])
def test_terminal_states_accept_no_action(terminal: S) -> None:
    assert terminal.is_terminal
    request = request_in(terminal)
    for action in A:
        with pytest.raises(InvalidStatusTransition):
            perform(request, action)


@pytest.mark.parametrize(
    ("status", "action", "intruder"),
    [
        (S.BORRADOR, A.SUBMIT, STAFF),
        (S.BORRADOR, A.SUBMIT, ADMIN),
        (S.BORRADOR, A.SUBMIT, OTHER_MENTOR),  # mentor ajeno: sin ownership
        (S.ENVIADA, A.START_REVIEW, MENTOR),
        (S.ENVIADA, A.START_REVIEW, ADMIN),
        (S.EN_REVISION, A.APPROVE, MENTOR),
        (S.EN_REVISION, A.APPROVE, ADMIN),
        (S.EN_REVISION, A.REJECT, MENTOR),
        (S.EN_REVISION, A.REJECT, ADMIN),
        (S.EN_REVISION, A.REQUEST_CORRECTION, MENTOR),
        (S.EN_REVISION, A.REQUEST_CORRECTION, ADMIN),
        (S.CORRECCION_SOLICITADA, A.RESUBMIT, STAFF),
        (S.CORRECCION_SOLICITADA, A.RESUBMIT, OTHER_MENTOR),
    ],
)
def test_wrong_role_or_non_owner_is_forbidden(status: S, action: A, intruder) -> None:
    request = request_in(status)
    with pytest.raises(Forbidden):
        perform(request, action, actor=intruder)
    assert request.status is status


@pytest.mark.parametrize("blank", ["", "   ", None])
def test_reason_is_required_to_reject_and_to_request_correction(blank) -> None:
    request = request_in(S.EN_REVISION)
    with pytest.raises(InvalidValue):
        request.reject(STAFF, NOW, blank)
    with pytest.raises(InvalidValue):
        request.request_correction(STAFF, NOW, blank)
    assert request.status is S.EN_REVISION and request.corrections == []


def test_submit_requires_a_complete_product_and_does_not_mutate() -> None:
    request = new_draft()
    with pytest.raises(IncompleteProduct) as error:
        request.submit(MENTOR, NOW, FilledForm.empty(request.id, FORM))
    assert error.value.missing == ("cedula", "titulo", "anio", "revista")  # orden del formulario
    assert request.status is S.BORRADOR and request.submitted_at is None


def test_product_of_another_request_is_rejected() -> None:
    request, other = new_draft(), new_draft()
    with pytest.raises(InvalidValue):
        request.submit(MENTOR, NOW, complete_form(other.id))


def test_full_lifecycle_records_reviewer_dates_and_corrections() -> None:
    request = new_draft()
    article = complete_form(request.id)
    assert request.submitted_at is None and request.reviewer_id is None

    request.submit(MENTOR, NOW, article)
    assert request.status is S.ENVIADA and request.submitted_at == NOW

    request.start_review(STAFF, NOW)
    assert request.reviewer_id == STAFF.user_id

    change = request.request_correction(STAFF, NOW, "  Falta el DOI  ")
    assert change.reason == "Falta el DOI"
    assert request.reviewed_at == NOW
    assert request.open_correction is not None and request.open_correction.is_open

    request.resubmit(MENTOR, NOW, article)
    assert request.status is S.REENVIADA  # type: ignore[comparison-overlap]
    assert request.open_correction is None
    assert request.corrections[0].resolved_at == NOW

    request.start_review(OTHER_STAFF, NOW)  # otro revisor puede tomar la reenviada
    assert request.reviewer_id == OTHER_STAFF.user_id
    request.request_correction(STAFF, NOW, "Segunda ronda")
    assert len(request.corrections) == 2 and request.open_correction is not None

    request.resubmit(MENTOR, NOW, article)
    request.start_review(STAFF, NOW)
    request.approve(STAFF, NOW, "Todo en orden")
    assert request.status is S.APROBADA


def test_resubmit_without_open_correction_is_an_invalid_state() -> None:
    request = request_in(S.CORRECCION_SOLICITADA)
    request.corrections.clear()  # inconsistencia simulada
    with pytest.raises(InvalidRequestState):
        request.resubmit(MENTOR, NOW, complete_form(request.id))


def test_create_draft_only_for_mentors() -> None:
    for actor in (STAFF, ADMIN):
        with pytest.raises(Forbidden):
            new_draft(actor)
    request = new_draft()
    assert request.status is S.BORRADOR and request.mentor_id == MENTOR.user_id


def test_creation_history_starts_from_nothing() -> None:
    from app.domain.entities.research_product_request import ResearchProductRequest
    from app.domain.value_objects.request_number import RequestNumber

    request, change = ResearchProductRequest.create_draft(
        actor=MENTOR,
        request_number=RequestNumber(2026, 7),
        form_version_id=1,
        product_type_id=1,
        now=NOW,
    )
    assert change.previous_status is None and change.new_status is S.BORRADOR
    assert change.request_id == request.id and change.changed_by == MENTOR.user_id


@pytest.mark.parametrize("status", list(S))
def test_owner_can_edit_only_in_editable_states(status: S) -> None:
    request = request_in(status)
    if status in EDITABLE_STATUSES:
        request.ensure_editable_by(MENTOR)
    else:
        with pytest.raises(InvalidRequestState):
            request.ensure_editable_by(MENTOR)


@pytest.mark.parametrize("intruder", [OTHER_MENTOR, STAFF, ADMIN])
def test_only_the_owner_mentor_can_edit(intruder) -> None:
    with pytest.raises(Forbidden):
        new_draft().ensure_editable_by(intruder)


def test_register_edit_checks_version_and_touches_the_root() -> None:
    request = new_draft()
    with pytest.raises(ConcurrentModification):
        request.register_edit(MENTOR, NOW, expected_version=request.version + 1)
    later = NOW.replace(hour=15)
    request.register_edit(MENTOR, later, expected_version=request.version)
    assert request.updated_at == later
