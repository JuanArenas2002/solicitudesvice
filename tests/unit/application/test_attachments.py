import hashlib
from datetime import UTC

import pytest

from app.application.commands.forms import CreateProductTypeCommand, ReplaceFormDraftCommand
from app.domain.enums.audit_action import AuditAction
from app.domain.enums.request_status import RequestStatus as S
from app.domain.enums.role import Role
from app.domain.exceptions.errors import (
    AttachmentLimitReached,
    AttachmentNotFound,
    CedulaLocked,
    DuplicateAttachment,
    FileTooLarge,
    Forbidden,
    InvalidRequestState,
    InvalidValue,
    RequestNotFound,
)
from app.domain.services.attachment_rules import MAX_FILES_PER_REQUEST
from tests.unit.application.conftest import CTX, World
from tests.unit.application.test_requests import Cast

PDF = b"%PDF-1.7\n"


def pdf(text: str = "") -> bytes:
    return PDF + text.encode()


@pytest.fixture
def cast(world: World) -> Cast:
    return Cast(world)


def draft_with_cedula(cast: Cast, cedula: str = "1003895357", actor=None):
    detail = cast.new(actor)
    return cast.world.update_answers().execute(
        actor or cast.mentor, detail.request.id, {"cedula": cedula}, detail.request.version, CTX
    )


# ---------------- estructura de carpetas ----------------
def test_files_go_to_cedula_product_and_numbered_request_folders(world: World, cast: Cast) -> None:
    first = draft_with_cedula(cast)
    a = world.upload().execute(
        cast.mentor, first.request.id, "soporte_articulo", "xxx.pdf", pdf("a"), CTX
    )
    b = world.upload().execute(
        cast.mentor, first.request.id, "soporte_articulo", "zzzz.pdf", pdf("b"), CTX
    )
    assert a.storage_key == "1003895357/Articulos/Solicitud 1/xxx.pdf"
    assert b.storage_key == "1003895357/Articulos/Solicitud 1/zzzz.pdf"
    assert world.storage.files[a.storage_key] == pdf("a")

    second = draft_with_cedula(cast)  # misma persona y producto: Solicitud 2
    c = world.upload().execute(
        cast.mentor, second.request.id, "soporte_articulo", "xxx.pdf", pdf("c"), CTX
    )
    assert c.storage_key == "1003895357/Articulos/Solicitud 2/xxx.pdf"

    other_person = draft_with_cedula(cast, "52123456")  # otra cédula: vuelve a empezar en 1
    d = world.upload().execute(
        cast.mentor, other_person.request.id, "soporte_articulo", "x.pdf", pdf("d"), CTX
    )
    assert d.storage_key == "52123456/Articulos/Solicitud 1/x.pdf"


def test_the_number_counts_per_person_and_per_product(world: World, cast: Cast) -> None:
    from tests.unit.application.test_requests import REQUIRED  # noqa: F401

    articles = draft_with_cedula(cast)
    world.upload().execute(
        cast.mentor, articles.request.id, "soporte_articulo", "a.pdf", pdf("1"), CTX
    )

    # segundo producto ("DT") con su carpeta propia
    admin = world.actor_for(world.add_user(Role.ADMIN, email="dt@example.org"))
    product, draft = world.create_product_type().execute(
        admin, CreateProductTypeCommand("DT", "Desarrollo tecnológico", folder_name="DT"), CTX
    )
    assert product.id is not None and draft.id is not None
    world.replace_draft().execute(
        admin,
        ReplaceFormDraftCommand(
            draft.id,
            [
                {
                    "title": "Datos",
                    "fields": [
                        {
                            "key": "cedula",
                            "label": "Cédula",
                            "type": "CEDULA",
                            "required_to_submit": True,
                        },
                        {
                            "key": "soporte",
                            "label": "Acta",
                            "type": "SUPPORT",
                            "allowed_types": ["pdf"],
                        },
                    ],
                }
            ],
        ),
        CTX,
    )
    world.publish().execute(admin, draft.id, CTX)
    dt = world.create_request().execute(cast.mentor, product.id, CTX)
    dt = world.update_answers().execute(
        cast.mentor, dt.request.id, {"cedula": "1003895357"}, dt.request.version, CTX
    )
    file = world.upload().execute(cast.mentor, dt.request.id, "soporte", "acta.pdf", pdf("2"), CTX)
    assert file.storage_key == "1003895357/DT/Solicitud 1/acta.pdf"  # DT cuenta aparte de Articulos


# ---------------- reglas de carga ----------------
def test_the_cedula_must_be_answered_first(world: World, cast: Cast) -> None:
    detail = cast.new()
    with pytest.raises(InvalidValue) as error:
        world.upload().execute(
            cast.mentor, detail.request.id, "soporte_articulo", "a.pdf", PDF, CTX
        )
    assert error.value.field == "cedula"
    assert world.storage.files == {} and world.db.state.folders == {}


def test_names_are_deduplicated_and_sanitized(world: World, cast: Cast) -> None:
    rid = draft_with_cedula(cast).request.id
    first = world.upload().execute(
        cast.mentor, rid, "soporte_articulo", "../../Informe final.pdf", pdf("1"), CTX
    )
    second = world.upload().execute(
        cast.mentor, rid, "soporte_articulo", "informe FINAL.pdf", pdf("2"), CTX
    )
    assert first.file_name == "Informe final.pdf"
    assert second.file_name == "informe FINAL (2).pdf"  # mismo nombre sin distinguir mayúsculas
    assert all(key.startswith("1003895357/Articulos/Solicitud 1/") for key in world.storage.files)


def test_duplicates_limits_and_invalid_files_are_rejected(world: World, cast: Cast) -> None:
    rid = draft_with_cedula(cast).request.id
    world.upload().execute(cast.mentor, rid, "soporte_articulo", "a.pdf", pdf("igual"), CTX)
    with pytest.raises(DuplicateAttachment):
        world.upload().execute(cast.mentor, rid, "soporte_articulo", "copia.pdf", pdf("igual"), CTX)
    with pytest.raises(InvalidValue):
        world.upload().execute(cast.mentor, rid, "soporte_articulo", "malo.exe", b"MZ", CTX)
    with pytest.raises(InvalidValue):
        world.upload().execute(cast.mentor, rid, "soporte_articulo", "falso.pdf", b"<html>", CTX)
    with pytest.raises(FileTooLarge):
        world.upload(max_bytes=10).execute(
            cast.mentor, rid, "soporte_articulo", "grande.pdf", pdf("x" * 50), CTX
        )
    for i in range(MAX_FILES_PER_REQUEST - 1):
        world.upload().execute(cast.mentor, rid, "soporte_articulo", f"f{i}.pdf", pdf(str(i)), CTX)
    with pytest.raises(AttachmentLimitReached):
        world.upload().execute(cast.mentor, rid, "soporte_articulo", "uno-mas.pdf", pdf("z"), CTX)
    assert len(world.db.state.attachments) == len(world.storage.files) == MAX_FILES_PER_REQUEST


def test_a_failed_database_write_leaves_no_orphan_file(
    world: World, cast: Cast, monkeypatch: pytest.MonkeyPatch
) -> None:
    rid = draft_with_cedula(cast).request.id
    world.upload().execute(cast.mentor, rid, "soporte_articulo", "a.pdf", pdf("1"), CTX)
    before = dict(world.storage.files)

    class Boom(Exception):
        pass

    def broken_add(self: object, attachment: object) -> None:
        raise Boom

    monkeypatch.setattr("tests.unit.application.fakes.FakeAttachmentRepository.add", broken_add)
    with pytest.raises(Boom):
        world.upload().execute(cast.mentor, rid, "soporte_articulo", "b.pdf", pdf("2"), CTX)
    assert world.storage.files == before  # el archivo escrito se borró


def test_a_storage_failure_stores_nothing_in_the_database(world: World, cast: Cast) -> None:
    rid = draft_with_cedula(cast).request.id
    world.storage.fail_on_save = True
    with pytest.raises(OSError):
        world.upload().execute(cast.mentor, rid, "soporte_articulo", "a.pdf", pdf("1"), CTX)
    assert world.db.state.attachments == {}
    assert world.audit_of(AuditAction.ATTACHMENT_UPLOADED) == []


# ---------------- permisos y estados ----------------
def test_only_the_owner_uploads_and_only_while_editable(world: World, cast: Cast) -> None:
    rid = draft_with_cedula(cast).request.id
    with pytest.raises(RequestNotFound):  # IDOR
        world.upload().execute(cast.other, rid, "soporte_articulo", "a.pdf", PDF, CTX)
    with pytest.raises(RequestNotFound):  # el borrador es privado
        world.upload().execute(cast.staff, rid, "soporte_articulo", "a.pdf", PDF, CTX)
    sent = cast.in_status(S.ENVIADA).request.id
    for actor in (cast.staff, cast.admin):
        with pytest.raises(Forbidden):
            world.upload().execute(actor, sent, "soporte_articulo", "a.pdf", PDF, CTX)
    with pytest.raises(InvalidRequestState):
        world.upload().execute(
            cast.mentor, sent, "soporte_articulo", "a.pdf", PDF, CTX
        )  # enviada: congelada
    corrected = cast.in_status(S.CORRECCION_SOLICITADA).request.id
    world.upload().execute(
        cast.mentor, corrected, "soporte_articulo", "correccion.pdf", pdf("c"), CTX
    )  # sí en corrección


def test_download_is_for_the_owner_and_the_staff_but_not_for_admin_or_strangers(
    world: World, cast: Cast
) -> None:
    detail = cast.in_status(S.BORRADOR)
    rid = detail.request.id
    attachment = world.upload().execute(
        cast.mentor, rid, "soporte_articulo", "a.pdf", pdf("dato"), CTX
    )
    assert b"".join(world.download().execute(cast.mentor, rid, attachment.id).content) == pdf(
        "dato"
    )

    world.submit().execute(cast.mentor, rid, CTX)
    assert b"".join(world.download().execute(cast.staff, rid, attachment.id).content) == pdf("dato")
    with pytest.raises(Forbidden):  # el admin ve la solicitud, pero no descarga soportes
        world.download().execute(cast.admin, rid, attachment.id)
    with pytest.raises(RequestNotFound):
        world.download().execute(cast.other, rid, attachment.id)
    with pytest.raises(AttachmentNotFound):
        world.download().execute(cast.staff, rid, __import__("uuid").uuid4())


def test_an_attachment_is_only_reachable_through_its_own_request(world: World, cast: Cast) -> None:
    mine = draft_with_cedula(cast).request.id
    other = draft_with_cedula(cast).request.id
    attachment = world.upload().execute(
        cast.mentor, mine, "soporte_articulo", "a.pdf", pdf("1"), CTX
    )
    with pytest.raises(AttachmentNotFound):  # mismo dueño, otra solicitud: no hay atajo
        world.download().execute(cast.mentor, other, attachment.id)
    with pytest.raises(AttachmentNotFound):
        world.delete_attachment().execute(cast.mentor, other, attachment.id, CTX)


def test_listing_shows_metadata_to_everyone_who_can_see_the_request(
    world: World, cast: Cast
) -> None:
    rid = cast.in_status(S.BORRADOR).request.id
    world.upload().execute(cast.mentor, rid, "soporte_articulo", "a.pdf", pdf("1"), CTX)
    world.submit().execute(cast.mentor, rid, CTX)
    for actor in (cast.mentor, cast.staff, cast.admin):
        names = {a.file_name for a in world.list_attachments().execute(actor, rid)}
        assert names == {"articulo.pdf", "a.pdf"}
    with pytest.raises(RequestNotFound):
        world.list_attachments().execute(cast.other, rid)


# ---------------- eliminar ----------------
def test_delete_removes_record_and_file_and_is_audited(world: World, cast: Cast) -> None:
    rid = draft_with_cedula(cast).request.id
    attachment = world.upload().execute(
        cast.mentor, rid, "soporte_articulo", "a.pdf", pdf("1"), CTX
    )
    with pytest.raises(RequestNotFound):
        world.delete_attachment().execute(cast.other, rid, attachment.id, CTX)

    world.delete_attachment().execute(cast.mentor, rid, attachment.id, CTX)

    assert world.db.state.attachments == {} and world.storage.files == {}
    (entry,) = world.audit_of(AuditAction.ATTACHMENT_DELETED)
    assert entry.detail["sha256"] == hashlib.sha256(pdf("1")).hexdigest()
    with pytest.raises(AttachmentNotFound):
        world.delete_attachment().execute(cast.mentor, rid, attachment.id, CTX)


def test_delete_is_only_possible_while_the_request_is_editable(world: World, cast: Cast) -> None:
    detail = cast.in_status(S.BORRADOR)
    rid = detail.request.id
    attachment = world.upload().execute(
        cast.mentor, rid, "soporte_articulo", "a.pdf", pdf("1"), CTX
    )
    world.submit().execute(cast.mentor, rid, CTX)
    for actor in (cast.mentor,):
        with pytest.raises(InvalidRequestState):
            world.delete_attachment().execute(actor, rid, attachment.id, CTX)
    with pytest.raises(Forbidden):
        world.delete_attachment().execute(cast.staff, rid, attachment.id, CTX)
    assert len(world.storage.files) == 2  # el del formulario completo + este


def test_a_missing_file_does_not_break_the_delete(world: World, cast: Cast) -> None:
    rid = draft_with_cedula(cast).request.id
    attachment = world.upload().execute(
        cast.mentor, rid, "soporte_articulo", "a.pdf", pdf("1"), CTX
    )
    world.storage.files.clear()  # el archivo ya no estaba en disco
    world.delete_attachment().execute(cast.mentor, rid, attachment.id, CTX)
    assert world.db.state.attachments == {}


def test_a_database_record_without_a_file_is_reported_not_crashed(world: World, cast: Cast) -> None:
    rid = draft_with_cedula(cast).request.id
    attachment = world.upload().execute(
        cast.mentor, rid, "soporte_articulo", "a.pdf", pdf("1"), CTX
    )
    world.storage.files.clear()
    with pytest.raises(AttachmentNotFound):
        world.download().execute(cast.mentor, rid, attachment.id)


# ---------------- la cédula se bloquea con soportes ----------------
def test_the_cedula_is_locked_once_there_are_attachments(world: World, cast: Cast) -> None:
    detail = draft_with_cedula(cast)
    rid = detail.request.id
    attachment = world.upload().execute(
        cast.mentor, rid, "soporte_articulo", "a.pdf", pdf("1"), CTX
    )
    current = world.get_request().execute(cast.mentor, rid)

    same = world.update_answers().execute(  # repetir la misma cédula no cambia nada
        cast.mentor, rid, {"cedula": "1.003.895.357", "titulo": "T"}, current.request.version, CTX
    )
    assert same.filled.cedula == "1003895357"
    for change in ({"cedula": "52123456"}, {"cedula": None}):
        with pytest.raises(CedulaLocked):
            world.update_answers().execute(cast.mentor, rid, change, same.request.version, CTX)
    # otros campos siguen editables y el árbol de carpetas no cambia
    assert world.storage.files.keys() == {attachment.storage_key}
    assert UTC is not None
