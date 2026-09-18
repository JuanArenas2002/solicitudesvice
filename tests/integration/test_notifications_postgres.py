# ruff: noqa: F811
"""Notificaciones al mentor, asignaciones para el admin e ISSN sin guion (PostgreSQL + HTTP)."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.database.models.notification import NotificationModel
from tests.integration.test_api_postgres import API, ok
from tests.integration.test_attachments_postgres import (  # noqa: F401  (fixtures compartidos)
    http,
    new_request,
    pdf,
    people,
    send,
)
from tests.integration.test_review_features_postgres import (  # noqa: F401
    FakeJournals,
    answers,
    journals,
    publish,
)

pytestmark = pytest.mark.integration


def submitted(http: TestClient, people: dict[str, dict[str, str]]) -> tuple[str, int]:
    product_id = publish(http, people["admin"], people["staff"])
    rid = new_request(http, people["mentor"], product_id, "1003895357")
    ok(send(http, people["mentor"], rid, "a.pdf", pdf(rid), field="acta"), 201)
    ok(http.post(f"{API}/requests/{rid}/submit", headers=people["mentor"]))
    return rid, product_id


def test_the_mentor_is_notified_of_every_change_made_by_staff(
    http: TestClient, people: dict[str, dict[str, str]], session_factory: sessionmaker[Session]
) -> None:
    staff, mentor, other = people["staff"], people["mentor"], people["other"]
    rid, _ = submitted(http, people)
    assert ok(http.get(f"{API}/notifications/unread-count", headers=mentor)) == {"unread": 0}

    ok(http.post(f"{API}/requests/{rid}/review", headers=staff))
    ok(
        http.post(
            f"{API}/requests/{rid}/request-correction",
            headers=staff,
            json={"description": "Falta la fecha"},
        )
    )
    ok(
        http.post(
            f"{API}/requests/{rid}/change-status",
            headers=staff,
            json={"status": "APROBADA", "reason": "Aprobada por comité"},
        )
    )

    assert ok(http.get(f"{API}/notifications/unread-count", headers=mentor)) == {"unread": 3}
    listed = ok(http.get(f"{API}/notifications", headers=mentor))
    assert listed["unread"] == 3 and listed["total"] == 3
    assert [(n["status"], n["reason"]) for n in listed["items"]] == [
        ("APROBADA", "Aprobada por comité"),
        ("CORRECCION_SOLICITADA", "Falta la fecha"),
        ("EN_REVISION", None),
    ]
    first = listed["items"][0]
    assert first["request_id"] == rid and first["request_number"].startswith("SOL-")
    assert first["read_at"] is None

    # nadie más las ve ni las puede tocar
    for headers in (other, staff, people["admin"]):
        assert ok(http.get(f"{API}/notifications", headers=headers))["total"] == 0
    assert (
        http.post(
            f"{API}/notifications/read", headers=other, json={"ids": [first["id"]]}
        ).status_code
        == 204
    )
    assert ok(http.get(f"{API}/notifications/unread-count", headers=mentor)) == {"unread": 3}

    # leer una, luego todas
    assert (
        http.post(
            f"{API}/notifications/read", headers=mentor, json={"ids": [first["id"]]}
        ).status_code
        == 204
    )
    assert ok(http.get(f"{API}/notifications/unread-count", headers=mentor)) == {"unread": 2}
    unread = ok(http.get(f"{API}/notifications?unread_only=true", headers=mentor))
    assert [n["status"] for n in unread["items"]] == ["CORRECCION_SOLICITADA", "EN_REVISION"]
    assert http.post(f"{API}/notifications/read", headers=mentor, json={}).status_code == 204
    assert ok(http.get(f"{API}/notifications/unread-count", headers=mentor)) == {"unread": 0}
    assert ok(http.get(f"{API}/notifications", headers=mentor))["total"] == 3

    # sin sesión y con datos inválidos
    assert http.get(f"{API}/notifications").status_code == 401
    assert (
        http.post(
            f"{API}/notifications/read", headers=mentor, json={"ids": ["no-uuid"]}
        ).status_code
        == 422
    )
    assert http.get(f"{API}/notifications?page_size=500", headers=mentor).status_code == 422

    with session_factory() as session:
        assert len(session.scalars(select(NotificationModel)).all()) == 3


def test_what_the_mentor_does_himself_notifies_nobody(
    http: TestClient, people: dict[str, dict[str, str]]
) -> None:
    submitted(http, people)
    for role in ("mentor", "staff", "admin"):
        assert ok(http.get(f"{API}/notifications/unread-count", headers=people[role])) == {
            "unread": 0
        }


def test_the_database_rejects_a_blank_reason_or_a_missing_owner(
    http: TestClient,
    people: dict[str, dict[str, str]],
    session_factory: sessionmaker[Session],
) -> None:
    staff = people["staff"]
    rid, _ = submitted(http, people)
    ok(http.post(f"{API}/requests/{rid}/review", headers=staff))
    with session_factory() as session:
        good = session.scalars(select(NotificationModel)).one()
        for changes in ({"reason": "   "}, {"user_id": uuid.uuid4()}, {"status_id": 99}):
            values = {
                "id": uuid.uuid4(),
                "user_id": good.user_id,
                "request_id": good.request_id,
                "status_id": good.status_id,
                "reason": None,
            }
            with session_factory() as attempt:
                attempt.add(NotificationModel(**{**values, **changes}))
                with pytest.raises(IntegrityError):
                    attempt.commit()


def test_the_admin_sees_who_reviews_what(
    http: TestClient, people: dict[str, dict[str, str]]
) -> None:
    admin, staff, mentor = people["admin"], people["staff"], people["mentor"]
    product_id = publish(http, admin, staff)  # también se lo asigna a `staff`
    staff_id = ok(http.get(f"{API}/auth/me", headers=staff))["id"]
    assert ok(http.get(f"{API}/users/product-assignments", headers=admin)) == {
        staff_id: [product_id]
    }
    for headers in (staff, mentor):
        assert http.get(f"{API}/users/product-assignments", headers=headers).status_code == 403
    ok(http.put(f"{API}/users/{staff_id}/products", headers=admin, json={"product_type_ids": []}))
    assert ok(http.get(f"{API}/users/product-assignments", headers=admin)) == {}


def test_the_issn_hyphen_is_optional_everywhere(
    http: TestClient, people: dict[str, dict[str, str]], journals: FakeJournals
) -> None:
    admin, staff, mentor = people["admin"], people["staff"], people["mentor"]
    rid = new_request(http, mentor, publish(http, admin, staff), "1003895357")

    assert ok(answers(http, mentor, rid, issn="12345679"))["answers"]["issn"] == "1234-5679"
    assert ok(answers(http, mentor, rid, issn=" 1234 5679 "))["answers"]["issn"] == "1234-5679"
    assert (
        answers(http, mentor, rid, issn="00000000").status_code == 422
    )  # sigue validando el catálogo
    assert ok(http.get(f"{API}/journals/12345679", headers=mentor))["title"] == "Revista de Pruebas"
    assert http.get(f"{API}/journals/1234567", headers=mentor).status_code == 422
