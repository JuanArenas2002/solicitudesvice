from datetime import date
from uuid import uuid4

import pytest

from app.application.dto.page import PageRequest
from app.application.dto.requests import RequestDetail
from app.application.queries.requests import RequestFilter
from app.domain.enums.audit_action import AuditAction
from app.domain.enums.form_status import FormStatus
from app.domain.enums.request_status import RequestStatus as S
from app.domain.enums.role import Role
from app.domain.exceptions.errors import (
    ConcurrentModification,
    Forbidden,
    FormVersionNotFound,
    IncompleteProduct,
    InvalidRequestState,
    InvalidStatusTransition,
    InvalidValue,
    ProductTypeNotFound,
    RequestNotFound,
)
from app.domain.value_objects.actor import Actor
from tests.unit.application.conftest import CTX, World

PDF_BYTES = b"%PDF-1.7\nsoporte"
REQUIRED = {
    "cedula": "1003895357",
    "titulo": "Un estudio",
    "anio_publicacion": 2025,
    "revista": "Revista de Pruebas",
}


class Cast:
    """Un mentor, otro mentor, un administrativo y un admin sobre el formulario de artículos."""

    def __init__(self, world: World) -> None:
        self.world = world
        self.product_id = world.article_product()
        self.mentor = world.actor_for(world.add_user(Role.MENTOR))
        self.other = world.actor_for(world.add_user(Role.MENTOR))
        self.staff = world.actor_for(world.add_user(Role.ADMINISTRATIVO))
        self.admin = world.actor_for(world.add_user(Role.ADMIN))

    def new(self, mentor: Actor | None = None) -> RequestDetail:
        return self.world.create_request().execute(mentor or self.mentor, self.product_id, CTX)

    def fill(self, detail: RequestDetail, **answers: object) -> RequestDetail:
        filled = self.world.update_answers().execute(
            self.mentor, detail.request.id, answers or REQUIRED, detail.request.version, CTX
        )
        if not answers:  # "completo" = respuestas obligatorias + el soporte obligatorio
            self.world.upload().execute(
                self.mentor, detail.request.id, "soporte_articulo", "articulo.pdf", PDF_BYTES, CTX
            )
            filled = self.world.get_request().execute(self.mentor, detail.request.id)
        return filled

    def in_status(self, status: S) -> RequestDetail:
        detail = self.fill(self.new())
        rid = detail.request.id
        w = self.world
        if status is S.BORRADOR:
            return detail
        detail = w.submit().execute(self.mentor, rid, CTX)
        if status is S.ENVIADA:
            return detail
        detail = w.start_review().execute(self.staff, rid, CTX)
        if status is S.EN_REVISION:
            return detail
        if status is S.APROBADA:
            return w.approve().execute(self.staff, rid, None, CTX)
        if status is S.RECHAZADA:
            return w.reject().execute(self.staff, rid, "No aplica", CTX)
        detail = w.request_correction().execute(self.staff, rid, "Falta el DOI", CTX)
        if status is S.CORRECCION_SOLICITADA:
            return detail
        return w.resubmit().execute(self.mentor, rid, CTX)  # REENVIADA


@pytest.fixture
def cast(world: World) -> Cast:
    return Cast(world)


# ---------------- crear ----------------
def test_mentor_creates_a_draft_with_the_published_form(world: World, cast: Cast) -> None:
    detail = cast.new()

    assert detail.request.status is S.BORRADOR and detail.request.mentor_id == cast.mentor.user_id
    assert str(detail.request.request_number) == f"SOL-{world.clock.now().year}-000001"
    assert (
        detail.product_type.code == "ARTICULO" and detail.filled.form.status is FormStatus.PUBLICADA
    )
    assert dict(detail.filled.answers) == {} and detail.request.version == 1
    (change,) = world.db.state.history
    assert (change.previous_status, change.new_status) == (None, S.BORRADOR)
    (entry,) = world.audit_of(AuditAction.REQUEST_CREATED)
    assert entry.entity_id == detail.request.id and entry.actor_id == cast.mentor.user_id
    assert cast.new().request.request_number.sequence == 2  # números consecutivos


@pytest.mark.parametrize("who", ["staff", "admin"])
def test_only_mentors_create_requests_and_no_number_is_burned(cast: Cast, who: str) -> None:
    with pytest.raises(Forbidden):
        cast.world.create_request().execute(getattr(cast, who), cast.product_id, CTX)
    assert cast.new().request.request_number.sequence == 1  # el rechazo no consumió número


def test_cannot_create_for_unknown_inactive_or_unpublished_products(
    world: World, cast: Cast
) -> None:
    with pytest.raises(ProductTypeNotFound):
        world.create_request().execute(cast.mentor, 999, CTX)
    world.db.state.product_types[cast.product_id].is_active = False
    with pytest.raises(ProductTypeNotFound):
        cast.new()
    world.db.state.product_types[cast.product_id].is_active = True
    (form,) = world.db.state.forms.values()
    form.status = FormStatus.RETIRADA  # sin formulario vigente
    with pytest.raises(FormVersionNotFound):
        cast.new()


# ---------------- respuestas ----------------
def test_answers_are_validated_saved_and_versioned(world: World, cast: Cast) -> None:
    detail = cast.new()
    saved = cast.fill(detail, titulo="  Un estudio  ", anio_publicacion=2025, doi="10.1234/x")

    assert dict(saved.filled.answers) == {
        "titulo": "Un estudio",
        "anio_publicacion": 2025,
        "doi": "10.1234/x",
    }
    assert saved.request.version == detail.request.version + 1
    (entry,) = world.audit_of(AuditAction.REQUEST_UPDATED)
    assert entry.detail == {"changed": ["anio_publicacion", "doi", "titulo"]}  # sin valores

    cleared = world.update_answers().execute(
        cast.mentor, saved.request.id, {"doi": "", "titulo": "Nuevo"}, saved.request.version, CTX
    )
    assert dict(cleared.filled.answers) == {"titulo": "Nuevo", "anio_publicacion": 2025}


def test_invalid_answers_are_all_or_nothing(world: World, cast: Cast) -> None:
    detail = cast.fill(cast.new(), titulo="Original")
    for bad in ({"anio_publicacion": 1800}, {"doi": "mal"}, {"no_existe": "x"}, {"issn": "12"}):
        with pytest.raises(InvalidValue):
            world.update_answers().execute(
                cast.mentor,
                detail.request.id,
                {"titulo": "Cambiado", **bad},
                detail.request.version,
                CTX,
            )
    stored = world.get_request().execute(cast.mentor, detail.request.id)
    assert dict(stored.filled.answers) == {"titulo": "Original"}
    assert stored.request.version == detail.request.version


def test_stale_version_is_a_concurrency_conflict(world: World, cast: Cast) -> None:
    detail = cast.new()
    cast.fill(detail, titulo="Primero")  # otra pestaña guardó antes
    with pytest.raises(ConcurrentModification):
        world.update_answers().execute(
            cast.mentor, detail.request.id, {"titulo": "Segundo"}, detail.request.version, CTX
        )


def test_only_the_owner_edits_and_only_in_editable_states(world: World, cast: Cast) -> None:
    detail = cast.new()
    rid, version = detail.request.id, detail.request.version
    with pytest.raises(RequestNotFound):  # IDOR: ni siquiera sabe que existe
        world.update_answers().execute(cast.other, rid, {"titulo": "x"}, version, CTX)
    with pytest.raises(RequestNotFound):  # el borrador es privado del mentor
        world.update_answers().execute(cast.staff, rid, {"titulo": "x"}, version, CTX)
    submitted = cast.in_status(S.ENVIADA)
    for actor in (cast.staff, cast.admin):
        with pytest.raises(Forbidden):
            world.update_answers().execute(
                actor, submitted.request.id, {"titulo": "x"}, submitted.request.version, CTX
            )
    with pytest.raises(InvalidRequestState):  # enviada: congelada
        world.update_answers().execute(
            cast.mentor, submitted.request.id, {"titulo": "x"}, submitted.request.version, CTX
        )


# ---------------- ciclo de vida completo ----------------
def test_full_lifecycle_with_correction_round(world: World, cast: Cast) -> None:
    detail = cast.fill(cast.new())
    rid = detail.request.id

    submitted = world.submit().execute(cast.mentor, rid, CTX)
    assert submitted.request.status is S.ENVIADA and submitted.request.submitted_at is not None

    reviewing = world.start_review().execute(cast.staff, rid, CTX)
    assert reviewing.request.status is S.EN_REVISION
    assert reviewing.request.reviewer_id == cast.staff.user_id

    corrected = world.request_correction().execute(cast.staff, rid, "  Falta el DOI  ", CTX)
    assert corrected.request.status is S.CORRECCION_SOLICITADA
    (open_correction,) = world.corrections().execute(cast.mentor, rid)
    assert open_correction.is_open and open_correction.description == "Falta el DOI"

    fixed = world.update_answers().execute(  # en corrección el mentor vuelve a poder editar
        cast.mentor, rid, {"doi": "10.1234/x"}, corrected.request.version, CTX
    )
    assert fixed.filled.answers["doi"] == "10.1234/x"

    resubmitted = world.resubmit().execute(cast.mentor, rid, CTX)
    assert resubmitted.request.status is S.REENVIADA
    (closed,) = world.corrections().execute(cast.staff, rid)
    assert not closed.is_open and closed.resolved_at is not None

    world.start_review().execute(cast.staff, rid, CTX)
    approved = world.approve().execute(cast.staff, rid, "Todo en orden", CTX)
    assert approved.request.status is S.APROBADA and approved.request.reviewed_at is not None

    history = world.history().execute(cast.mentor, rid)
    assert [(h.previous_status, h.new_status) for h in history] == [
        (None, S.BORRADOR),
        (S.BORRADOR, S.ENVIADA),
        (S.ENVIADA, S.EN_REVISION),
        (S.EN_REVISION, S.CORRECCION_SOLICITADA),
        (S.CORRECCION_SOLICITADA, S.REENVIADA),
        (S.REENVIADA, S.EN_REVISION),
        (S.EN_REVISION, S.APROBADA),
    ]
    assert history[3].reason == "Falta el DOI" and history[3].changed_by == cast.staff.user_id
    assert world.audit_actions().count(AuditAction.REQUEST_APPROVED) == 1
    (rejection_free,) = world.audit_of(AuditAction.REQUEST_APPROVED)
    assert rejection_free.detail == {"from": "EN_REVISION", "to": "APROBADA"}


def test_rejection_requires_a_reason_and_is_final(world: World, cast: Cast) -> None:
    detail = cast.in_status(S.EN_REVISION)
    rid = detail.request.id
    with pytest.raises(InvalidValue):
        world.reject().execute(cast.staff, rid, "  ", CTX)
    rejected = world.reject().execute(cast.staff, rid, "Fuera del alcance", CTX)
    assert rejected.request.status is S.RECHAZADA
    for action in (
        lambda: world.approve().execute(cast.staff, rid, None, CTX),
        lambda: world.reject().execute(cast.staff, rid, "otra vez", CTX),
        lambda: world.start_review().execute(cast.staff, rid, CTX),
        lambda: world.request_correction().execute(cast.staff, rid, "x", CTX),
    ):
        with pytest.raises(InvalidStatusTransition):
            action()


def test_double_approval_is_rejected(world: World, cast: Cast) -> None:
    rid = cast.in_status(S.EN_REVISION).request.id
    world.approve().execute(cast.staff, rid, None, CTX)
    with pytest.raises(InvalidStatusTransition):
        world.approve().execute(cast.staff, rid, None, CTX)
    assert len(world.audit_of(AuditAction.REQUEST_APPROVED)) == 1
    assert len([h for h in world.db.state.history if h.new_status is S.APROBADA]) == 1


def test_incomplete_request_cannot_be_submitted_and_leaves_no_trace(
    world: World, cast: Cast
) -> None:
    detail = cast.fill(cast.new(), titulo="Solo el título")
    history_before = len(world.db.state.history)
    with pytest.raises(IncompleteProduct) as error:
        world.submit().execute(cast.mentor, detail.request.id, CTX)
    assert error.value.missing == (
        "cedula",
        "anio_publicacion",
        "revista",
        "soporte_articulo",
    )  # en el orden del formulario
    assert world.get_request().execute(cast.mentor, detail.request.id).request.status is S.BORRADOR
    assert len(world.db.state.history) == history_before
    assert world.audit_of(AuditAction.REQUEST_SUBMITTED) == []


# ---------------- roles y ownership ----------------
def test_role_restrictions_on_transitions(world: World, cast: Cast) -> None:
    sent = cast.in_status(S.ENVIADA).request.id
    reviewing = cast.in_status(S.EN_REVISION).request.id
    for actor in (cast.mentor, cast.admin):
        with pytest.raises(Forbidden):
            world.start_review().execute(actor, sent, CTX)
    for actor in (cast.mentor, cast.admin):
        with pytest.raises(Forbidden):
            world.approve().execute(actor, reviewing, None, CTX)
        with pytest.raises(Forbidden):
            world.reject().execute(actor, reviewing, "x", CTX)
        with pytest.raises(Forbidden):
            world.request_correction().execute(actor, reviewing, "x", CTX)
    draft = cast.fill(cast.new()).request.id
    with pytest.raises(RequestNotFound):  # el administrativo no ve borradores ajenos
        world.submit().execute(cast.staff, draft, CTX)
    with pytest.raises(Forbidden):  # el admin ve solicitudes enviadas, pero no las opera
        world.resubmit().execute(
            cast.admin, cast.in_status(S.CORRECCION_SOLICITADA).request.id, CTX
        )


@pytest.mark.parametrize("status", list(S))
def test_another_mentor_can_never_see_or_touch_a_request(
    world: World, cast: Cast, status: S
) -> None:
    rid = cast.in_status(status).request.id
    calls = (
        lambda: world.get_request().execute(cast.other, rid),
        lambda: world.history().execute(cast.other, rid),
        lambda: world.corrections().execute(cast.other, rid),
        lambda: world.submit().execute(cast.other, rid, CTX),
        lambda: world.resubmit().execute(cast.other, rid, CTX),
        lambda: world.update_answers().execute(cast.other, rid, {"titulo": "x"}, 1, CTX),
    )
    for call in calls:
        with pytest.raises(RequestNotFound):
            call()


def test_visibility_of_drafts(world: World, cast: Cast) -> None:
    draft = cast.new().request.id
    for actor in (cast.staff, cast.admin):
        with pytest.raises(RequestNotFound):
            world.get_request().execute(actor, draft)
    sent = cast.in_status(S.ENVIADA).request.id
    for actor in (cast.mentor, cast.staff, cast.admin):  # el admin: solo lectura
        assert world.get_request().execute(actor, sent).request.id == sent
        assert world.history().execute(actor, sent)
    with pytest.raises(RequestNotFound):
        world.get_request().execute(cast.mentor, uuid4())


# ---------------- listados ----------------
def test_listings_are_scoped_filtered_and_paginated(world: World, cast: Cast) -> None:
    cast.new()  # borrador del mentor
    sent = cast.in_status(S.ENVIADA)
    approved = cast.in_status(S.APROBADA)
    cast.new(cast.other)  # borrador del otro mentor

    mine = world.list_requests().execute(cast.mentor, RequestFilter(), PageRequest())
    assert mine.total == 3 and {i.mentor_id for i in mine.items} == {cast.mentor.user_id}
    theirs = world.list_requests().execute(cast.other, RequestFilter(), PageRequest())
    assert theirs.total == 1 and theirs.items[0].mentor_id == cast.other.user_id
    # un mentor no puede ampliar su alcance pidiendo otro mentor
    spoof = world.list_requests().execute(
        cast.mentor, RequestFilter(mentor_id=cast.other.user_id), PageRequest()
    )
    assert spoof.total == 3 and {i.mentor_id for i in spoof.items} == {cast.mentor.user_id}

    for viewer in (cast.staff, cast.admin):
        page = world.list_requests().execute(viewer, RequestFilter(), PageRequest())
        assert page.total == 2 and all(i.status is not S.BORRADOR for i in page.items)
    staff = cast.staff
    by_status = world.list_requests().execute(
        staff, RequestFilter(status=S.APROBADA), PageRequest()
    )
    assert [i.id for i in by_status.items] == [approved.request.id]
    by_number = world.list_requests().execute(
        staff, RequestFilter(request_number=str(sent.request.request_number)[:8]), PageRequest()
    )
    assert by_number.total == 2
    exact = world.list_requests().execute(
        staff, RequestFilter(request_number=str(sent.request.request_number)), PageRequest()
    )
    assert [i.id for i in exact.items] == [sent.request.id]
    by_mentor = world.list_requests().execute(
        staff, RequestFilter(mentor_id=cast.other.user_id), PageRequest()
    )
    assert by_mentor.total == 0  # el borrador ajeno sigue oculto
    by_type = world.list_requests().execute(
        staff, RequestFilter(product_type_id=cast.product_id), PageRequest(1, 1)
    )
    assert by_type.total == 2 and len(by_type.items) == 1 and by_type.total_pages == 2
    today = world.clock.now().date()
    assert (
        world.list_requests()
        .execute(staff, RequestFilter(date_from=today, date_to=today), PageRequest())
        .total
        == 2
    )
    assert (
        world.list_requests()
        .execute(staff, RequestFilter(date_to=date(2000, 1, 1)), PageRequest())
        .total
        == 0
    )
    row = by_status.items[0]
    assert (row.product_type_code, row.mentor_name, row.status) == (
        "ARTICULO",
        "Ana Pérez",
        S.APROBADA,
    )


def test_summaries_expose_the_same_data_as_the_detail(world: World, cast: Cast) -> None:
    detail = cast.in_status(S.ENVIADA)
    (row,) = world.list_requests().execute(cast.mentor, RequestFilter(), PageRequest()).items
    assert (row.id, row.version, row.form_version_id) == (
        detail.request.id,
        detail.request.version,
        detail.request.form_version_id,
    )
