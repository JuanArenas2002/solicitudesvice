"""Soportes: carpetas <cédula>/<producto>/Solicitud N contra PostgreSQL real y por HTTP."""

import os
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.application.use_cases.attachments.manage_attachments import (
    DeleteAttachment,
    UploadAttachment,
)
from app.config.settings import Settings
from app.domain.enums.role import Role
from app.domain.exceptions.errors import CedulaLocked, DuplicateAttachment
from app.infrastructure.database.models.request_attachment import RequestAttachmentModel
from app.infrastructure.database.models.storage import StorageCounterModel, StorageFolderModel
from app.infrastructure.storage.local import LocalFileStorage
from app.interfaces.api.app import create_app
from tests.integration.test_api_postgres import (
    API,
    ORIGIN,
    login,
    make_user,
    ok,
    publish_book,
)
from tests.integration.test_requests_postgres import CTX, World

pytestmark = pytest.mark.integration

MAX_BYTES = 2048


def pdf(text: str = "") -> bytes:
    return b"%PDF-1.7\n" + text.encode()


# ======================= casos de uso + repositorios =======================
@pytest.fixture
def world(session_factory: sessionmaker[Session]) -> World:
    return World(session_factory)


@pytest.fixture
def storage(tmp_path: Path) -> LocalFileStorage:
    return LocalFileStorage(tmp_path / "storage")


def draft_with(world: World, cedula: str, actor: Any = None) -> Any:
    detail = world.update(world.create(actor), {"cedula": cedula}, actor)
    return detail.request.id


def test_folders_are_numbered_per_person_and_product_on_disk_and_in_the_database(
    world: World, storage: LocalFileStorage, tmp_path: Path
) -> None:
    upload = UploadAttachment(world.uow, world.clock, storage, 1024 * 1024)
    first, second = draft_with(world, "1003895357"), draft_with(world, "1003895357")
    other = draft_with(world, "52123456")

    a = upload.execute(world.mentor, first, "soporte", "xxx.pdf", pdf("a"), CTX)
    b = upload.execute(world.mentor, first, "soporte", "zzzz.pdf", pdf("b"), CTX)
    c = upload.execute(world.mentor, second, "soporte", "xxx.pdf", pdf("c"), CTX)
    d = upload.execute(world.mentor, other, "soporte", "xxx.pdf", pdf("d"), CTX)

    assert [x.storage_key for x in (a, b, c, d)] == [
        "1003895357/Todo/Solicitud 1/xxx.pdf",
        "1003895357/Todo/Solicitud 1/zzzz.pdf",
        "1003895357/Todo/Solicitud 2/xxx.pdf",
        "52123456/Todo/Solicitud 1/xxx.pdf",
    ]
    root = tmp_path / "storage"
    assert sorted(p.relative_to(root).as_posix() for p in root.rglob("*.pdf")) == sorted(
        x.storage_key for x in (a, b, c, d)
    )
    assert (root / a.storage_key).read_bytes() == pdf("a")
    with world.session_factory() as session:
        rows = session.execute(
            select(
                StorageFolderModel.cedula,
                StorageFolderModel.sequence,
                StorageFolderModel.request_id,
            ).order_by(StorageFolderModel.cedula, StorageFolderModel.sequence)
        ).all()
        counters = session.execute(
            select(StorageCounterModel.cedula, StorageCounterModel.last_value).order_by(
                StorageCounterModel.cedula
            )
        ).all()
    assert [(r.cedula, r.sequence) for r in rows] == [
        ("1003895357", 1),
        ("1003895357", 2),
        ("52123456", 1),
    ]
    assert [tuple(c) for c in counters] == [("1003895357", 2), ("52123456", 1)]
    # la carpeta se asigna una sola vez: más archivos de la misma solicitud reutilizan la carpeta
    assert world.count(StorageFolderModel) == 3


def test_concurrent_first_uploads_get_distinct_consecutive_folders(
    world: World, storage: LocalFileStorage
) -> None:
    requests = [draft_with(world, "1003895357") for _ in range(6)]
    upload = UploadAttachment(world.uow, world.clock, storage, 1024 * 1024)

    def go(item: tuple[int, Any]) -> str:
        i, rid = item
        return upload.execute(world.mentor, rid, "soporte", "a.pdf", pdf(str(i)), CTX).storage_key

    with ThreadPoolExecutor(max_workers=6) as pool:
        keys = list(pool.map(go, enumerate(requests)))
    assert sorted(keys) == [f"1003895357/Todo/Solicitud {n}/a.pdf" for n in range(1, 7)]
    assert world.count(StorageFolderModel) == 6


def test_the_cedula_is_locked_after_the_first_attachment(
    world: World, storage: LocalFileStorage
) -> None:
    rid = draft_with(world, "1003895357")
    UploadAttachment(world.uow, world.clock, storage, 1024 * 1024).execute(
        world.mentor, rid, "soporte", "a.pdf", pdf(), CTX
    )
    detail = world.get(rid)
    with pytest.raises(CedulaLocked):
        world.update(detail, {"cedula": "52123456"})
    assert world.get(rid).filled.cedula == "1003895357"


def test_a_failed_upload_leaves_neither_rows_nor_files(
    world: World, storage: LocalFileStorage, tmp_path: Path
) -> None:
    rid = draft_with(world, "1003895357")
    upload = UploadAttachment(world.uow, world.clock, storage, 1024 * 1024)
    upload.execute(world.mentor, rid, "soporte", "a.pdf", pdf("1"), CTX)
    with pytest.raises(DuplicateAttachment):
        upload.execute(world.mentor, rid, "soporte", "copia.pdf", pdf("1"), CTX)  # mismo contenido
    assert world.count(RequestAttachmentModel) == 1
    files = [p for p in (tmp_path / "storage").rglob("*") if p.is_file()]
    assert len(files) == 1


def test_delete_removes_the_row_the_file_and_keeps_the_folder_number(
    world: World, storage: LocalFileStorage, tmp_path: Path
) -> None:
    rid = draft_with(world, "1003895357")
    upload = UploadAttachment(world.uow, world.clock, storage, 1024 * 1024)
    a = upload.execute(world.mentor, rid, "soporte", "a.pdf", pdf("1"), CTX)
    DeleteAttachment(world.uow, world.clock, storage).execute(world.mentor, rid, a.id, CTX)
    assert world.count(RequestAttachmentModel) == 0
    assert not (tmp_path / "storage" / a.storage_key).exists()
    b = upload.execute(world.mentor, rid, "soporte", "b.pdf", pdf("2"), CTX)
    assert b.storage_key == "1003895357/Todo/Solicitud 1/b.pdf"  # el número no se reasigna


# ======================= restricciones de la base de datos =======================
def test_database_rejects_invalid_folders_and_duplicate_files(
    world: World, storage: LocalFileStorage, session_factory: sessionmaker[Session]
) -> None:
    rid = draft_with(world, "1003895357")
    attachment = UploadAttachment(world.uow, world.clock, storage, 1024 * 1024).execute(
        world.mentor, rid, "soporte", "a.pdf", pdf("1"), CTX
    )
    other = draft_with(world, "1003895357")
    with world.session_factory() as session:
        product_id = session.scalar(select(StorageFolderModel.product_type_id))
    assert product_id is not None

    def insert_folder(**values: Any) -> None:
        with session_factory() as session:
            session.add(StorageFolderModel(**values))
            session.commit()

    base = {"request_id": other, "cedula": "1003895357", "product_type_id": product_id}
    for bad in (
        {"sequence": 1},  # repite (cédula, producto, número) de la primera solicitud
        {"sequence": 0},
        {"sequence": 5, "cedula": "12"},
        {"sequence": 5, "cedula": "../123456"},
    ):
        with pytest.raises(IntegrityError):
            insert_folder(**{**base, **bad})
    with pytest.raises(IntegrityError):  # una carpeta por solicitud
        insert_folder(**{**base, "request_id": rid, "sequence": 9})

    with session_factory() as session:  # el mismo contenido no puede repetirse en la solicitud
        row = session.get(RequestAttachmentModel, attachment.id)
        assert row is not None
        session.add(
            RequestAttachmentModel(
                id=uuid.uuid4(),
                request_id=rid,
                file_name="otro.pdf",
                mime_type=row.mime_type,
                file_size=row.file_size,
                sha256=row.sha256,
                storage_key=f"{row.storage_key}.bis",
                uploaded_by=row.uploaded_by,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_a_folder_cannot_outlive_its_request_or_product(
    world: World, storage: LocalFileStorage, session_factory: sessionmaker[Session]
) -> None:
    from app.infrastructure.database.models.research_request import ResearchProductRequestModel

    rid = draft_with(world, "1003895357")
    UploadAttachment(world.uow, world.clock, storage, 1024 * 1024).execute(
        world.mentor, rid, "soporte", "a.pdf", pdf(), CTX
    )
    with session_factory() as session:
        request = session.get(ResearchProductRequestModel, rid)
        assert request is not None
        session.delete(request)
        with pytest.raises(IntegrityError):  # RESTRICT: los soportes no se pierden en silencio
            session.commit()


# ======================= HTTP =======================
@pytest.fixture(scope="module")
def http(engine: Any, tmp_path_factory: pytest.TempPathFactory) -> Iterator[TestClient]:
    root = tmp_path_factory.mktemp("uploads")
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        environment="test",
        database_url=os.environ["TEST_DATABASE_URL"],
        jwt_secret_key="s" * 48,  # type: ignore[arg-type]
        cookie_secure=False,
        journals_url="",  # las pruebas no salen a la red
        cors_origins=[ORIGIN],
        storage_root=str(root),
        attachment_max_bytes=MAX_BYTES,
    )
    with TestClient(create_app(settings), base_url="http://testserver") as api:
        api.storage_root = root
        yield api


@pytest.fixture
def people(http: TestClient, session_factory: sessionmaker[Session]) -> dict[str, dict[str, str]]:
    fresh = TestClient(http.app, base_url="http://testserver")  # cookies aparte
    roles = (
        ("admin", Role.ADMIN),
        ("staff", Role.ADMINISTRATIVO),
        ("mentor", Role.MENTOR),
        ("other", Role.MENTOR),
    )
    return {name: login(fresh, make_user(session_factory, role)) for name, role in roles}


def new_request(client: TestClient, headers: dict[str, str], product_id: int, cedula: str) -> str:
    created = ok(
        client.post(f"{API}/requests", headers=headers, json={"product_type_id": product_id}), 201
    )
    ok(
        client.patch(
            f"{API}/requests/{created['id']}/answers",
            headers=headers,
            json={"version": created["version"], "answers": {"cedula": cedula, "titulo": "T"}},
        )
    )
    return str(created["id"])


def send(
    client: TestClient,
    headers: dict[str, str],
    rid: str,
    name: str,
    body: bytes,
    field: str = "soporte",
) -> Any:
    return client.post(
        f"{API}/requests/{rid}/attachments",
        headers=headers,
        data={"field_key": field},
        files={"file": (name, body)},
    )


def test_upload_list_download_and_delete_over_http(
    http: TestClient,
    people: dict[str, dict[str, str]],
) -> None:
    admin, staff, mentor, other = (people[k] for k in ("admin", "staff", "mentor", "other"))
    product_id, _ = publish_book(http, admin, people["staff"])
    rid = new_request(http, mentor, product_id, "1003895357")
    base = f"{API}/requests/{rid}/attachments"
    root: Path = http.storage_root

    first = ok(send(http, mentor, rid, "xxx.pdf", pdf("uno")), 201)
    second = ok(send(http, mentor, rid, "zzzz.pdf", pdf("dos")), 201)
    assert first["folder"] == second["folder"] == "1003895357/Libro/Solicitud 1"
    assert (root / "1003895357" / "Libro" / "Solicitud 1" / "xxx.pdf").read_bytes() == pdf("uno")
    assert "storage_key" not in first  # no se expone la ruta interna, solo la carpeta lógica

    listed = ok(http.get(base, headers=mentor))
    assert [a["file_name"] for a in listed] == ["xxx.pdf", "zzzz.pdf"]

    # descarga: fuerza la descarga y no deja que el navegador interprete el contenido
    download = http.get(f"{base}/{first['id']}/download", headers=mentor)
    assert download.status_code == 200 and download.content == pdf("uno")
    assert download.headers["content-type"] == "application/pdf"
    assert download.headers["content-disposition"].startswith("attachment;")
    assert download.headers["x-content-type-options"] == "nosniff"
    assert download.headers["cache-control"] == "private, no-store"

    # IDOR: otro mentor no ve ni la solicitud ni sus soportes
    assert http.get(base, headers=other).status_code == 404
    assert http.get(f"{base}/{first['id']}/download", headers=other).status_code == 404
    assert send(http, other, rid, "x.pdf", pdf("x")).status_code == 404
    # sin token
    assert http.get(base).status_code == 401

    # el borrador es privado: el personal no lo ve todavía
    assert http.get(base, headers=staff).status_code == 404

    # la cédula queda bloqueada con soportes
    locked = http.patch(
        f"{API}/requests/{rid}/answers",
        headers=mentor,
        json={
            "version": ok(http.get(f"{API}/requests/{rid}", headers=mentor))["version"],
            "answers": {"cedula": "52123456"},
        },
    )
    assert locked.status_code == 409 and locked.json()["code"] == "CedulaLocked"

    # se elimina uno mientras es editable
    assert http.delete(f"{base}/{second['id']}", headers=mentor).status_code == 204
    assert not (root / "1003895357" / "Libro" / "Solicitud 1" / "zzzz.pdf").exists()
    assert http.delete(f"{base}/{second['id']}", headers=mentor).status_code == 404

    # enviada: personal y admin ven la lista; el personal descarga, el admin no; nadie sube/borra
    ok(http.post(f"{API}/requests/{rid}/submit", headers=mentor))
    for headers in (staff, admin):
        assert [a["id"] for a in ok(http.get(base, headers=headers))] == [first["id"]]
    assert http.get(f"{base}/{first['id']}/download", headers=staff).content == pdf("uno")
    assert http.get(f"{base}/{first['id']}/download", headers=admin).status_code == 403
    assert send(http, mentor, rid, "tarde.pdf", pdf("t")).status_code == 409
    assert http.delete(f"{base}/{first['id']}", headers=mentor).status_code == 409
    assert http.delete(f"{base}/{first['id']}", headers=staff).status_code == 403
    assert send(http, staff, rid, "s.pdf", pdf("s")).status_code == 403


def test_second_request_of_the_same_person_gets_the_next_folder(
    http: TestClient,
    people: dict[str, dict[str, str]],
) -> None:
    admin, mentor = people["admin"], people["mentor"]
    product_id, _ = publish_book(http, admin, people["staff"])
    one = new_request(http, mentor, product_id, "1003895357")
    two = new_request(http, mentor, product_id, "1003895357")
    assert ok(send(http, mentor, one, "a.pdf", pdf("1")), 201)["folder"].endswith("Solicitud 1")
    assert ok(send(http, mentor, two, "a.pdf", pdf("2")), 201)["folder"].endswith("Solicitud 2")


def test_invalid_uploads_are_rejected_with_clear_errors(
    http: TestClient,
    people: dict[str, dict[str, str]],
) -> None:
    admin, mentor = people["admin"], people["mentor"]
    product_id, _ = publish_book(http, admin, people["staff"])
    rid = new_request(http, mentor, product_id, "1003895357")
    no_cedula = ok(
        http.post(f"{API}/requests", headers=mentor, json={"product_type_id": product_id}), 201
    )["id"]

    assert send(http, mentor, no_cedula, "a.pdf", pdf()).status_code == 422  # falta la cédula
    assert send(http, mentor, rid, "virus.exe", b"MZ\x90").status_code == 422
    assert send(http, mentor, rid, "falso.pdf", b"<html>").status_code == 422
    assert send(http, mentor, rid, "vacio.pdf", b"").status_code == 422
    too_big = send(http, mentor, rid, "grande.pdf", pdf("x" * MAX_BYTES))
    assert too_big.status_code == 413
    assert http.post(f"{API}/requests/{rid}/attachments", headers=mentor).status_code == 422
    ok(send(http, mentor, rid, "a.pdf", pdf("1")), 201)
    duplicate = send(http, mentor, rid, "copia.pdf", pdf("1"))
    assert duplicate.status_code == 409 and duplicate.json()["code"] == "DuplicateAttachment"
    bad_id = f"{API}/requests/{uuid.uuid4()}/attachments"
    assert http.get(bad_id, headers=mentor).status_code == 404
    assert http.get(f"{API}/requests/no-es-uuid/attachments", headers=mentor).status_code == 422


def test_products_expose_their_support_folder(
    http: TestClient,
    people: dict[str, dict[str, str]],
) -> None:
    admin = people["admin"]
    created = ok(
        http.post(
            f"{API}/product-types",
            headers=admin,
            json={"code": "DT", "name": "Desarrollo tecnológico", "folder_name": "DT"},
        ),
        201,
    )
    assert created["folder_name"] == "DT"
    derived = ok(
        http.post(
            f"{API}/product-types",
            headers=admin,
            json={"code": "OTRO", "name": "Artículo científico"},
        ),
        201,
    )
    assert derived["folder_name"] == "Articulo_cientifico"
    clash = http.post(
        f"{API}/product-types",
        headers=admin,
        json={
            "code": "DOS",
            "name": "Otro nombre",
            "folder_name": "dt",
        },  # sin distinguir mayúsculas
    )
    assert clash.status_code == 409
    invalid = http.post(
        f"{API}/product-types",
        headers=admin,
        json={"code": "TRES", "name": "Tres", "folder_name": "../fuera"},
    )
    assert invalid.status_code == 422


def test_upload_counts_are_consistent(
    http: TestClient,
    people: dict[str, dict[str, str]],
    session_factory: sessionmaker[Session],
) -> None:
    admin, mentor = people["admin"], people["mentor"]
    product_id, _ = publish_book(http, admin, people["staff"])
    rid = new_request(http, mentor, product_id, "1003895357")
    for i in range(3):
        ok(send(http, mentor, rid, f"f{i}.pdf", pdf(str(i))), 201)
    with session_factory() as session:
        total = session.scalar(
            select(func.count())
            .select_from(RequestAttachmentModel)
            .where(RequestAttachmentModel.request_id == uuid.UUID(rid))
        )
    assert total == 3
