"""Soportes por campo, revisores por producto, cambio manual de estado y validación de ISSN."""

from uuid import uuid4

import pytest

from app.application.dto.page import PageRequest
from app.application.queries.requests import RequestFilter
from app.domain.enums.audit_action import AuditAction
from app.domain.enums.request_status import RequestStatus as S
from app.domain.enums.role import Role
from app.domain.exceptions.errors import (
    Forbidden,
    IncompleteProduct,
    InvalidRequestState,
    InvalidStatusTransition,
    InvalidValue,
    JournalNotFound,
    JournalServiceUnavailable,
    ProductTypeNotFound,
    RequestNotFound,
    UserNotFound,
)
from app.domain.value_objects.actor import Actor
from tests.unit.application.conftest import CTX, World
from tests.unit.application.test_requests import PDF_BYTES, REQUIRED, Cast

PAGE = PageRequest(1, 50)


@pytest.fixture
def cast(world: World) -> Cast:
    return Cast(world)


def with_cedula(cast: Cast):
    detail = cast.new()
    return cast.world.update_answers().execute(
        cast.mentor, detail.request.id, {"cedula": "1003895357"}, detail.request.version, CTX
    )


# ======================= soportes dentro de su campo =======================
def test_each_support_field_only_takes_its_own_document_types(world: World, cast: Cast) -> None:
    rid = with_cedula(cast).request.id
    upload = world.upload()
    with pytest.raises(InvalidValue) as error:  # el artículo publicado solo admite PDF
        upload.execute(cast.mentor, rid, "soporte_articulo", "carta.docx", b"PK\x03\x04x", CTX)
    assert error.value.field == "file" and "pdf" in error.value.message
    # la carta de aceptación sí admite Word
    ok = upload.execute(cast.mentor, rid, "soporte_aceptacion", "carta.docx", b"PK\x03\x04x", CTX)
    assert ok.field_key == "soporte_aceptacion" and ok.file_name == "carta.docx"


@pytest.mark.parametrize("key", ["titulo", "cedula", "no_existe", ""])
def test_files_can_only_go_into_support_fields(world: World, cast: Cast, key: str) -> None:
    rid = with_cedula(cast).request.id
    with pytest.raises(InvalidValue) as error:
        world.upload().execute(cast.mentor, rid, key, "a.pdf", PDF_BYTES, CTX)
    assert error.value.field == "field_key"
    assert world.db.state.attachments == {}


def test_a_required_support_blocks_the_submission_until_it_has_a_file(
    world: World, cast: Cast
) -> None:
    detail = cast.fill(cast.new(), **REQUIRED)  # respuestas completas, sin soporte
    assert detail.filled.missing_for_submission() == ("soporte_articulo",)
    with pytest.raises(IncompleteProduct) as error:
        world.submit().execute(cast.mentor, detail.request.id, CTX)
    assert error.value.missing == ("soporte_articulo",)

    world.upload().execute(
        cast.mentor, detail.request.id, "soporte_articulo", "a.pdf", PDF_BYTES, CTX
    )
    assert world.submit().execute(cast.mentor, detail.request.id, CTX).request.status is S.ENVIADA


def test_the_detail_reports_which_supports_are_missing(world: World, cast: Cast) -> None:
    detail = cast.fill(cast.new(), **REQUIRED)
    assert "soporte_articulo" in detail.filled.missing_for_submission()
    world.upload().execute(
        cast.mentor, detail.request.id, "soporte_aceptacion", "c.pdf", PDF_BYTES, CTX
    )
    after = world.get_request().execute(cast.mentor, detail.request.id)
    assert after.filled.attached_keys == {
        "soporte_aceptacion"
    }  # el opcional no cumple el obligatorio
    assert after.filled.missing_for_submission() == ("soporte_articulo",)


def test_deleting_the_only_support_makes_the_field_missing_again(world: World, cast: Cast) -> None:
    detail = cast.fill(cast.new())  # completo, con su soporte
    (attachment,) = world.list_attachments().execute(cast.mentor, detail.request.id)
    world.delete_attachment().execute(cast.mentor, detail.request.id, attachment.id, CTX)
    with pytest.raises(IncompleteProduct):
        world.submit().execute(cast.mentor, detail.request.id, CTX)


# ======================= administrativos con productos asignados =======================
def staff_with(world: World, *product_ids: int) -> Actor:
    user = world.add_user(Role.ADMINISTRATIVO)
    admin = world.actor_for(world.add_user(Role.ADMIN))
    world.set_user_products().execute(admin, user.id, product_ids, CTX)
    tokens = world.login_as(user).tokens
    return world.authenticate().execute(tokens.access_token)  # alcance real, leído de la BD


def test_only_the_admin_assigns_products_and_only_to_staff(world: World, cast: Cast) -> None:
    admin = cast.admin
    staff_user = world.add_user(Role.ADMINISTRATIVO)
    mentor_user = world.add_user(Role.MENTOR)

    assert world.set_user_products().execute(admin, staff_user.id, [cast.product_id], CTX) == {
        cast.product_id
    }
    assert world.get_user_products().execute(admin, staff_user.id) == {cast.product_id}
    (entry,) = world.audit_of(AuditAction.USER_PRODUCTS_ASSIGNED)
    assert entry.entity_id == staff_user.id and entry.detail == {
        "product_type_ids": [cast.product_id]
    }

    for outsider in (cast.staff, cast.mentor):
        with pytest.raises(Forbidden):
            world.set_user_products().execute(outsider, staff_user.id, [], CTX)
        with pytest.raises(Forbidden):
            world.get_user_products().execute(outsider, staff_user.id)
    with pytest.raises(InvalidValue):  # un mentor no revisa productos
        world.set_user_products().execute(admin, mentor_user.id, [cast.product_id], CTX)
    with pytest.raises(ProductTypeNotFound):
        world.set_user_products().execute(admin, staff_user.id, [999], CTX)
    with pytest.raises(UserNotFound):
        world.set_user_products().execute(admin, uuid4(), [], CTX)
    assert world.get_user_products().execute(admin, staff_user.id) == {cast.product_id}  # intacto

    world.set_user_products().execute(admin, staff_user.id, [], CTX)  # se puede quitar todo
    assert world.get_user_products().execute(admin, staff_user.id) == frozenset()


def test_authentication_loads_the_product_scope_from_the_database(world: World, cast: Cast) -> None:
    assert staff_with(world, cast.product_id).product_scope == frozenset({cast.product_id})
    assert staff_with(world).product_scope == frozenset()  # sin productos: no ve nada
    mentor_user = world.add_user(Role.MENTOR)
    tokens = world.login_as(mentor_user).tokens
    assert world.authenticate().execute(tokens.access_token).product_scope is None


def test_staff_only_sees_and_handles_requests_of_its_assigned_products(
    world: World, cast: Cast
) -> None:
    sent = cast.in_status(S.ENVIADA).request.id
    mine, nothing = staff_with(world, cast.product_id), staff_with(world)

    assert world.list_requests().execute(mine, RequestFilter(), PAGE).total == 1
    assert world.list_requests().execute(nothing, RequestFilter(), PAGE).total == 0
    assert world.get_request().execute(mine, sent).request.id == sent
    for action in (
        lambda: world.get_request().execute(nothing, sent),
        lambda: world.history().execute(nothing, sent),
        lambda: world.corrections().execute(nothing, sent),
        lambda: world.list_attachments().execute(nothing, sent),
        lambda: world.start_review().execute(nothing, sent, CTX),
        lambda: world.change_status().execute(nothing, sent, S.APROBADA, "x", CTX),
    ):
        with pytest.raises(RequestNotFound):  # ni siquiera se revela que existe
            action()
    assert world.start_review().execute(mine, sent, CTX).request.status is S.EN_REVISION
    # el admin sigue viendo todo
    assert world.list_requests().execute(cast.admin, RequestFilter(), PAGE).total == 1


# ======================= cambio manual de estado =======================
def test_staff_changes_the_status_and_it_shows_in_history_and_audit(
    world: World, cast: Cast
) -> None:
    rid = cast.in_status(S.APROBADA).request.id
    detail = world.change_status().execute(
        cast.staff, rid, S.EN_REVISION, "Se reabre por un error", CTX
    )

    assert detail.request.status is S.EN_REVISION
    last = world.history().execute(cast.staff, rid)[-1]
    assert (last.previous_status, last.new_status, last.reason) == (
        S.APROBADA,
        S.EN_REVISION,
        "Se reabre por un error",
    )
    (entry,) = world.audit_of(AuditAction.REQUEST_STATUS_CHANGED)
    assert (
        entry.detail == {"from": "APROBADA", "to": "EN_REVISION"}
        and entry.actor_id == cast.staff.user_id
    )


def test_returning_a_request_to_correction_gives_the_mentor_the_pen_back(
    world: World, cast: Cast
) -> None:
    rid = cast.in_status(S.APROBADA).request.id
    detail = world.change_status().execute(
        cast.staff, rid, S.CORRECCION_SOLICITADA, "Falta el DOI", CTX
    )
    assert detail.request.open_correction is not None
    world.update_answers().execute(
        cast.mentor, rid, {"doi": "10.1234/x"}, detail.request.version, CTX
    )


def test_change_status_rules(world: World, cast: Cast) -> None:
    rid = cast.in_status(S.ENVIADA).request.id
    for actor in (cast.mentor, cast.admin):
        with pytest.raises(Forbidden):
            world.change_status().execute(actor, rid, S.APROBADA, "x", CTX)
    with pytest.raises(InvalidValue):
        world.change_status().execute(cast.staff, rid, S.APROBADA, "", CTX)
    with pytest.raises(InvalidStatusTransition):
        world.change_status().execute(cast.staff, rid, S.BORRADOR, "x", CTX)
    with pytest.raises(InvalidStatusTransition):
        world.change_status().execute(cast.staff, rid, S.ENVIADA, "x", CTX)
    with pytest.raises(RequestNotFound):  # el borrador es privado del mentor
        draft = cast.fill(cast.new()).request.id
        world.change_status().execute(cast.staff, draft, S.APROBADA, "x", CTX)
    assert world.get_request().execute(cast.staff, rid).request.status is S.ENVIADA
    assert world.audit_of(AuditAction.REQUEST_STATUS_CHANGED) == []


def test_mentors_still_cannot_edit_after_a_manual_move_to_a_frozen_status(
    world: World, cast: Cast
) -> None:
    rid = cast.in_status(S.CORRECCION_SOLICITADA).request.id
    detail = world.change_status().execute(
        cast.staff, rid, S.EN_REVISION, "Ya lo corrigió por correo", CTX
    )
    assert detail.request.open_correction is None  # la corrección abierta se cerró
    with pytest.raises(InvalidRequestState):
        world.update_answers().execute(
            cast.mentor, rid, {"titulo": "x"}, detail.request.version, CTX
        )


# ======================= ISSN contra el catálogo de revistas =======================
KNOWN = "1234-5679"


def test_a_known_issn_is_saved(world: World, cast: Cast) -> None:
    detail = cast.fill(cast.new(), issn=KNOWN)
    assert detail.filled.answers["issn"] == KNOWN and world.journals.calls == [KNOWN]


def test_an_unknown_issn_is_rejected_when_saving(world: World, cast: Cast) -> None:
    detail = cast.new()
    with pytest.raises(InvalidValue) as error:
        cast.fill(detail, issn="0000-0000")
    assert error.value.field == "issn" and "0000-0000" in error.value.message
    assert dict(world.get_request().execute(cast.mentor, detail.request.id).filled.answers) == {}


def test_only_changed_issns_are_looked_up(world: World, cast: Cast) -> None:
    detail = cast.fill(cast.new(), issn=KNOWN)
    world.journals.calls.clear()
    cast.fill(world.get_request().execute(cast.mentor, detail.request.id), titulo="Otro")
    assert world.journals.calls == []  # el ISSN no cambió: no se vuelve a consultar


def test_an_outage_does_not_block_saving_a_draft(world: World, cast: Cast) -> None:
    world.journals.down = True
    assert cast.fill(cast.new(), issn=KNOWN).filled.answers["issn"] == KNOWN


def test_submitting_verifies_every_issn(world: World, cast: Cast) -> None:
    world.journals.known["8888-8887"] = "Otra"
    detail = cast.fill(cast.new(), issn=KNOWN, eissn="8888-8887")
    detail = cast.fill(detail)  # completa respuestas obligatorias y soporte
    world.journals.calls.clear()
    assert world.submit().execute(cast.mentor, detail.request.id, CTX).request.status is S.ENVIADA
    assert sorted(world.journals.calls) == sorted([KNOWN, "8888-8887"])


def test_submitting_is_refused_if_the_catalog_is_down_or_forgets_the_issn(
    world: World, cast: Cast
) -> None:
    world.journals.down = True
    detail = cast.fill(cast.new(), issn=KNOWN)
    detail = cast.fill(detail)
    with pytest.raises(JournalServiceUnavailable):
        world.submit().execute(cast.mentor, detail.request.id, CTX)
    world.journals.down = False
    del world.journals.known[KNOWN]  # el catálogo ya no lo conoce
    with pytest.raises(InvalidValue):
        world.submit().execute(cast.mentor, detail.request.id, CTX)
    assert world.get_request().execute(cast.mentor, detail.request.id).request.status is S.BORRADOR


def test_resubmitting_verifies_issns_too(world: World, cast: Cast) -> None:
    detail = cast.fill(cast.new(), issn=KNOWN)
    rid = cast.fill(detail).request.id
    world.submit().execute(cast.mentor, rid, CTX)
    world.start_review().execute(cast.staff, rid, CTX)
    world.request_correction().execute(cast.staff, rid, "Ajustar", CTX)
    world.journals.down = True
    with pytest.raises(JournalServiceUnavailable):
        world.resubmit().execute(cast.mentor, rid, CTX)
    world.journals.down = False
    assert world.resubmit().execute(cast.mentor, rid, CTX).request.status is S.REENVIADA


def test_lookup_journal(world: World, cast: Cast) -> None:
    journal = world.lookup_journal().execute(cast.mentor, KNOWN)
    assert journal.title == "Revista de Pruebas"
    with pytest.raises(JournalNotFound):
        world.lookup_journal().execute(cast.mentor, "0000-0000")
    with pytest.raises(InvalidValue):
        world.lookup_journal().execute(cast.mentor, "no-es-issn")
    world.journals.down = True
    with pytest.raises(JournalServiceUnavailable):
        world.lookup_journal().execute(cast.mentor, KNOWN)
