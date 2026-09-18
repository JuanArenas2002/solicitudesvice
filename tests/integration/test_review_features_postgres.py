# ruff: noqa: F811
"""Soportes por campo, revisores por producto, cambio de estado e ISSN (PostgreSQL + HTTP)."""

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.application.ports.services.journals import Journal
from app.domain.exceptions.errors import JournalServiceUnavailable
from app.infrastructure.database.models.form import FormFieldDocumentTypeModel
from app.infrastructure.database.models.request_attachment import RequestAttachmentModel
from app.infrastructure.database.models.user_product_assignment import UserProductAssignmentModel
from tests.integration.test_api_postgres import API, ok, publish_book
from tests.integration.test_attachments_postgres import (  # noqa: F401  (fixtures compartidos)
    http,
    new_request,
    pdf,
    people,
    send,
)

pytestmark = pytest.mark.integration

ISSN_FORM = {
    "sections": [
        {
            "title": "Datos",
            "fields": [
                {"key": "cedula", "label": "Cédula", "type": "CEDULA", "required_to_submit": True},
                {"key": "titulo", "label": "Título", "type": "TEXT", "required_to_submit": True},
                {"key": "issn", "label": "ISSN", "type": "ISSN"},
                {
                    "key": "acta",
                    "label": "Acta",
                    "type": "SUPPORT",
                    "help_text": "PDF o Word",
                    "allowed_types": ["pdf", "docx"],
                },
            ],
        }
    ]
}


class FakeJournals:
    def __init__(self) -> None:
        self.down = False
        self.known = {"1234-5679": "Revista de Pruebas"}

    def find(self, issn: str) -> Journal | None:
        if self.down:
            raise JournalServiceUnavailable("caído")
        title = self.known.get(issn)
        return Journal(title, "Editorial", "Colombia", issn, None, True) if title else None


@pytest.fixture
def journals(http: TestClient) -> Iterator[FakeJournals]:
    fake = FakeJournals()
    container = http.app.state.container  # type: ignore[attr-defined]
    original = container.journals
    container.journals = fake
    yield fake
    container.journals = original


def publish(client: TestClient, admin: dict[str, str], staff: dict[str, str]) -> int:
    code = "P" + uuid.uuid4().hex[:8].upper()
    product = ok(
        client.post(
            f"{API}/product-types",
            headers=admin,
            json={"code": code, "name": code, "folder_name": code},
        ),
        201,
    )
    versions = ok(client.get(f"{API}/product-types/{product['id']}/form-versions", headers=admin))
    ok(client.put(f"{API}/form-versions/{versions[0]['id']}", headers=admin, json=ISSN_FORM))
    ok(client.post(f"{API}/form-versions/{versions[0]['id']}/publish", headers=admin))
    me = ok(client.get(f"{API}/auth/me", headers=staff))
    ok(
        client.put(
            f"{API}/users/{me['id']}/products",
            headers=admin,
            json={"product_type_ids": [product["id"]]},
        )
    )
    return int(product["id"])


def answers(client: TestClient, headers: dict[str, str], rid: str, **values: object) -> Any:
    version = ok(client.get(f"{API}/requests/{rid}", headers=headers))["version"]
    return client.patch(
        f"{API}/requests/{rid}/answers",
        headers=headers,
        json={"version": version, "answers": values},
    )


# ======================= soportes por campo =======================
def test_the_form_builder_stores_and_returns_the_document_types(
    http: TestClient,
    people: dict[str, dict[str, str]],  # noqa: F811
    session_factory: sessionmaker[Session],
) -> None:
    admin, staff = people["admin"], people["staff"]
    product_id = publish(http, admin, staff)
    form = ok(http.get(f"{API}/product-types/{product_id}/form", headers=people["mentor"]))
    acta = next(f for f in form["sections"][0]["fields"] if f["key"] == "acta")
    assert acta["type"] == "SUPPORT" and acta["allowed_types"] == ["pdf", "docx"]
    cedula = form["sections"][0]["fields"][0]
    assert cedula["allowed_types"] == []

    with session_factory() as session:  # una fila por tipo permitido, normalizado
        assert session.scalars(select(FormFieldDocumentTypeModel.document_type_id)).all() != []

    # un soporte sin tipos de documento, o con tipos inexistentes, no se puede guardar
    draft = ok(http.post(f"{API}/product-types/{product_id}/form-versions", headers=admin), 201)
    for bad in ([], ["exe"]):
        invalid = {
            "sections": [
                {
                    "title": "S",
                    "fields": [
                        {
                            "key": "cedula",
                            "label": "C",
                            "type": "CEDULA",
                            "required_to_submit": True,
                        },
                        {"key": "acta", "label": "Acta", "type": "SUPPORT", "allowed_types": bad},
                    ],
                }
            ]
        }
        response = http.put(f"{API}/form-versions/{draft['id']}", headers=admin, json=invalid)
        assert response.status_code == 422 and response.json()["field"] == "acta"

    # el nuevo borrador conserva los tipos de documento de la versión publicada
    copy = next(f for f in draft["sections"][0]["fields"] if f["key"] == "acta")
    assert copy["allowed_types"] == ["pdf", "docx"]


def test_uploads_go_into_a_support_field_and_respect_its_types(
    http: TestClient,
    people: dict[str, dict[str, str]],  # noqa: F811
    session_factory: sessionmaker[Session],
) -> None:
    admin, staff, mentor = people["admin"], people["staff"], people["mentor"]
    product_id = publish(http, admin, staff)
    rid = new_request(http, mentor, product_id, "1003895357")

    docx = send(http, mentor, rid, "acta.docx", b"PK\x03\x04docx", field="acta")
    assert docx.status_code == 201 and docx.json()["field_key"] == "acta"
    for name, body, field in (
        ("foto.png", b"\x89PNG\r\n\x1a\n" + b"\0" * 8, "acta"),  # tipo que el campo no admite
        ("a.pdf", pdf("x"), "titulo"),  # el campo no es un soporte
        ("a.pdf", pdf("x"), "no_existe"),
    ):
        response = send(http, mentor, rid, name, body, field=field)
        assert response.status_code == 422, (name, field, response.text)

    listed = ok(http.get(f"{API}/requests/{rid}/attachments", headers=mentor))
    assert [(a["field_key"], a["file_name"]) for a in listed] == [("acta", "acta.docx")]

    with (
        session_factory() as session
    ):  # el soporte quedó ligado al campo y a la versión de la solicitud
        row = session.scalars(select(RequestAttachmentModel)).one()
        assert row.field_type_id == 14 and row.form_version_id is not None


def test_database_rejects_a_support_in_the_wrong_field_or_version(
    http: TestClient,
    people: dict[str, dict[str, str]],  # noqa: F811
    session_factory: sessionmaker[Session],
) -> None:
    admin, staff, mentor = people["admin"], people["staff"], people["mentor"]
    product_id = publish(http, admin, staff)
    other_product = publish(http, admin, staff)
    rid = new_request(http, mentor, product_id, "1003895357")
    ok(send(http, mentor, rid, "acta.docx", b"PK\x03\x04docx", field="acta"), 201)

    with session_factory() as session:
        good = session.scalars(select(RequestAttachmentModel)).one()
        from app.infrastructure.database.models.form import FormFieldModel, FormVersionModel

        other_field = session.scalars(
            select(FormFieldModel)
            .join(FormVersionModel, FormVersionModel.id == FormFieldModel.form_version_id)
            .where(FormVersionModel.product_type_id == other_product, FormFieldModel.key == "acta")
        ).one()
        titulo = session.scalars(
            select(FormFieldModel).where(
                FormFieldModel.form_version_id == good.form_version_id,
                FormFieldModel.key == "titulo",
            )
        ).one()

        def clone(**changes: object) -> RequestAttachmentModel:
            values = {
                "id": uuid.uuid4(),
                "request_id": good.request_id,
                "form_version_id": good.form_version_id,
                "field_id": good.field_id,
                "field_type_id": 14,
                "uploaded_by": good.uploaded_by,
                "file_name": "otro.pdf",
                "mime_type": "application/pdf",
                "file_size": 5,
                "sha256": "b" * 64,
                "storage_key": f"x/{uuid.uuid4()}",
            }
            return RequestAttachmentModel(**{**values, **changes})

        for changes in (
            {
                "field_id": other_field.id,
                "form_version_id": other_field.form_version_id,
            },  # otra versión
            {"field_id": other_field.id},  # campo de otra versión con la versión de la solicitud
            {"field_id": titulo.id, "field_type_id": titulo.field_type_id},  # no es de soporte
            {"field_type_id": 1},  # el tipo declarado no es el del campo
        ):
            with session_factory() as attempt:
                attempt.add(clone(**changes))
                with pytest.raises(IntegrityError):
                    attempt.commit()


# ======================= revisores con productos asignados =======================
def test_staff_only_reaches_the_products_assigned_by_the_admin(
    http: TestClient,
    people: dict[str, dict[str, str]],  # noqa: F811
    session_factory: sessionmaker[Session],
) -> None:
    admin, staff, mentor, other = (people[k] for k in ("admin", "staff", "mentor", "other"))
    assigned = publish(http, admin, staff)  # el helper también se lo asigna a `staff`
    unassigned = ok(
        http.post(
            f"{API}/product-types",
            headers=admin,
            json={"code": "OCULTO", "name": "Oculto", "folder_name": "Oculto"},
        ),
        201,
    )["id"]
    versions = ok(http.get(f"{API}/product-types/{unassigned}/form-versions", headers=admin))
    ok(http.put(f"{API}/form-versions/{versions[0]['id']}", headers=admin, json=ISSN_FORM))
    ok(http.post(f"{API}/form-versions/{versions[0]['id']}/publish", headers=admin))

    visible = new_request(http, mentor, assigned, "1003895357")
    hidden = new_request(http, other, unassigned, "52123456")
    for headers, rid in ((mentor, visible), (other, hidden)):
        ok(send(http, headers, rid, "a.pdf", pdf(rid), field="acta"), 201)
        ok(answers(http, headers, rid, titulo="T"))
        ok(http.post(f"{API}/requests/{rid}/submit", headers=headers))

    listed = ok(http.get(f"{API}/requests", headers=staff))
    assert [r["id"] for r in listed["items"]] == [visible]
    assert http.get(f"{API}/requests/{hidden}", headers=staff).status_code == 404
    assert http.post(f"{API}/requests/{hidden}/review", headers=staff).status_code == 404
    assert http.get(f"{API}/requests/{hidden}/attachments", headers=staff).status_code == 404
    assert http.get(f"{API}/requests/{visible}", headers=staff).status_code == 200
    # el admin sigue viendo ambas
    assert ok(http.get(f"{API}/requests", headers=admin))["total"] == 2

    # quitar la asignación se nota en la siguiente petición
    me = ok(http.get(f"{API}/auth/me", headers=staff))
    ok(http.put(f"{API}/users/{me['id']}/products", headers=admin, json={"product_type_ids": []}))
    assert ok(http.get(f"{API}/requests", headers=staff))["total"] == 0
    assert http.get(f"{API}/requests/{visible}", headers=staff).status_code == 404
    with session_factory() as session:
        assert session.scalars(select(UserProductAssignmentModel)).all() == []


def test_product_assignment_endpoint_rules(
    http: TestClient,
    people: dict[str, dict[str, str]],  # noqa: F811
) -> None:
    admin, staff, mentor = people["admin"], people["staff"], people["mentor"]
    product_id, _ = publish_book(http, admin)
    staff_id = ok(http.get(f"{API}/auth/me", headers=staff))["id"]
    mentor_id = ok(http.get(f"{API}/auth/me", headers=mentor))["id"]
    url = f"{API}/users/{staff_id}/products"
    body = {"product_type_ids": [product_id]}

    assert ok(http.put(url, headers=admin, json=body)) == body
    assert ok(http.get(url, headers=admin)) == body
    assert (
        ok(http.put(url, headers=admin, json={"product_type_ids": [product_id, product_id]}))
        == body
    )
    for headers in (staff, mentor):  # solo el administrador gestiona asignaciones
        assert http.get(url, headers=headers).status_code == 403
        assert http.put(url, headers=headers, json=body).status_code == 403
    assert (
        http.put(f"{API}/users/{mentor_id}/products", headers=admin, json=body).status_code == 422
    )
    assert http.put(url, headers=admin, json={"product_type_ids": [999999]}).status_code == 404
    assert (
        http.put(f"{API}/users/{uuid.uuid4()}/products", headers=admin, json=body).status_code
        == 404
    )
    assert http.put(url, headers=admin, json={"product_type_ids": "no"}).status_code == 422
    assert ok(http.get(url, headers=admin)) == body  # los intentos fallidos no cambiaron nada


# ======================= cambio manual de estado =======================
def test_staff_can_move_a_request_through_any_status_and_the_database_agrees(
    http: TestClient,
    people: dict[str, dict[str, str]],  # noqa: F811
) -> None:
    admin, staff, mentor = people["admin"], people["staff"], people["mentor"]
    product_id = publish(http, admin, staff)
    rid = new_request(http, mentor, product_id, "1003895357")
    ok(send(http, mentor, rid, "a.pdf", pdf("x"), field="acta"), 201)
    ok(http.post(f"{API}/requests/{rid}/submit", headers=mentor))
    url = f"{API}/requests/{rid}/change-status"

    path = [
        "APROBADA", "ENVIADA", "CORRECCION_SOLICITADA", "REENVIADA", "RECHAZADA",
        "EN_REVISION", "CORRECCION_SOLICITADA", "APROBADA", "EN_REVISION",
    ]  # fmt: skip
    for target in path:  # todas las combinaciones respetan las restricciones de la base de datos
        detail = ok(http.post(url, headers=staff, json={"status": target, "reason": f"a {target}"}))
        assert detail["status"] == target
        assert (detail["open_correction"] is not None) == (target == "CORRECCION_SOLICITADA")
    history = ok(http.get(f"{API}/requests/{rid}/history", headers=staff))
    assert [h["new_status"] for h in history][-len(path) :] == path
    assert history[-1]["reason"] == "a EN_REVISION" and history[-1]["previous_status"] == "APROBADA"

    # reglas
    assert (
        http.post(url, headers=staff, json={"status": "APROBADA", "reason": ""}).status_code == 422
    )
    assert http.post(url, headers=staff, json={"status": "APROBADA"}).status_code == 422
    assert (
        http.post(url, headers=staff, json={"status": "EN_REVISION", "reason": "x"}).status_code
        == 409
    )
    assert (
        http.post(url, headers=staff, json={"status": "BORRADOR", "reason": "x"}).status_code == 409
    )
    assert (
        http.post(url, headers=staff, json={"status": "NO_EXISTE", "reason": "x"}).status_code
        == 422
    )
    for headers in (mentor, admin):
        assert (
            http.post(url, headers=headers, json={"status": "APROBADA", "reason": "x"}).status_code
            == 403
        )


# ======================= ISSN contra el catálogo de revistas =======================
def test_issn_is_validated_against_the_journal_catalog_over_http(
    http: TestClient,
    people: dict[str, dict[str, str]],  # noqa: F811
    journals: FakeJournals,
) -> None:
    admin, staff, mentor = people["admin"], people["staff"], people["mentor"]
    product_id = publish(http, admin, staff)
    rid = new_request(http, mentor, product_id, "1003895357")

    assert answers(http, mentor, rid, issn="0000-0000").status_code == 422
    unknown = answers(http, mentor, rid, issn="0000-0000").json()
    assert unknown["field"] == "issn" and "0000-0000" in unknown["detail"]
    assert ok(answers(http, mentor, rid, issn="1234-5679"))["answers"]["issn"] == "1234-5679"

    journals.down = True  # sin catálogo el borrador se guarda igual...
    assert answers(http, mentor, rid, issn="1234-5679", titulo="Otro").status_code == 200
    ok(send(http, mentor, rid, "a.pdf", pdf("x"), field="acta"), 201)
    refused = http.post(f"{API}/requests/{rid}/submit", headers=mentor)  # ...pero no se envía
    assert refused.status_code == 503 and "ISSN" in refused.json()["detail"]
    assert ok(http.get(f"{API}/requests/{rid}", headers=mentor))["status"] == "BORRADOR"

    journals.down = False
    assert ok(http.post(f"{API}/requests/{rid}/submit", headers=mentor))["status"] == "ENVIADA"


def test_journal_lookup_endpoint(
    http: TestClient,
    people: dict[str, dict[str, str]],  # noqa: F811
    journals: FakeJournals,
) -> None:
    mentor = people["mentor"]
    found = ok(http.get(f"{API}/journals/1234-5679", headers=mentor))
    assert found["title"] == "Revista de Pruebas" and found["publisher"] == "Editorial"
    assert http.get(f"{API}/journals/0000-0000", headers=mentor).status_code == 404
    assert http.get(f"{API}/journals/no-es-issn", headers=mentor).status_code == 422
    assert http.get(f"{API}/journals/1234-5679").status_code == 401
    journals.down = True
    assert http.get(f"{API}/journals/1234-5679", headers=mentor).status_code == 503


def test_without_a_configured_catalog_issn_is_only_format_checked(
    http: TestClient,
    people: dict[str, dict[str, str]],  # noqa: F811
) -> None:
    admin, staff, mentor = people["admin"], people["staff"], people["mentor"]
    rid = new_request(http, mentor, publish(http, admin, staff), "1003895357")
    assert ok(answers(http, mentor, rid, issn="0000-0000"))["answers"]["issn"] == "0000-0000"
    assert http.get(f"{API}/journals/1234-5679", headers=mentor).status_code == 503
