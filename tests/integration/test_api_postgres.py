"""API HTTP de punta a punta (FastAPI + PostgreSQL real + Argon2 + JWT + cookies + CSRF)."""

import os
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy.orm import Session, sessionmaker

from app.config.settings import Settings
from app.domain.entities.user import User
from app.domain.enums.role import Role
from app.infrastructure.clock import SystemClock
from app.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork
from app.infrastructure.security.passwords import Argon2PasswordHasher
from app.interfaces.api.app import create_app

pytestmark = pytest.mark.integration

API = "/api/v1"
ORIGIN = "http://localhost:5173"
PASSWORD = "clave-segura-de-prueba-1"

BOOK_FORM = {
    "sections": [
        {
            "title": "Datos del libro",
            "fields": [
                {"key": "cedula", "label": "Cédula", "type": "CEDULA", "required_to_submit": True},
                {"key": "titulo", "label": "Título", "type": "TEXT", "required_to_submit": True},
                {
                    "key": "anio",
                    "label": "Año",
                    "type": "INTEGER",
                    "min_value": 1900,
                    "max_value": 2100,
                },
                {
                    "key": "idioma",
                    "label": "Idioma",
                    "type": "SINGLE_SELECT",
                    "options": [
                        {"value": "es", "label": "Español"},
                        {"value": "en", "label": "Inglés"},
                    ],
                },
                {"key": "isbn", "label": "ISBN", "type": "TEXT", "max_length": 20},
                {"key": "soporte", "label": "Acta", "type": "SUPPORT", "allowed_types": ["pdf"]},
            ],
        }
    ]
}


@pytest.fixture(scope="module")
def client(engine: Any) -> Iterator[TestClient]:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        environment="test",
        database_url=os.environ["TEST_DATABASE_URL"],
        jwt_secret_key="s" * 48,  # type: ignore[arg-type]
        cookie_secure=False,
        journals_url="",  # las pruebas no salen a la red
        cors_origins=[ORIGIN],
    )
    with TestClient(create_app(settings), base_url="http://testserver") as api:
        yield api


@pytest.fixture(autouse=True)
def fresh_cookies(client: TestClient) -> None:
    client.cookies.clear()


def make_user(session_factory: sessionmaker[Session], role: Role, password: str = PASSWORD) -> str:
    email = f"{uuid.uuid4().hex[:10]}@example.org"
    user = User.create(
        first_name="Ana",
        last_name=role.value.title(),
        email=email,
        password_hash=Argon2PasswordHasher().hash(password),
        role=role,
        now=SystemClock().now(),
    )
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.users.add(user)
        uow.commit()
    return email


def login(client: TestClient, email: str, password: str = PASSWORD) -> dict[str, str]:
    response = client.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def people(client: TestClient, session_factory: sessionmaker[Session]) -> dict[str, dict[str, str]]:
    """Encabezados de autenticación de un admin, un administrativo y dos mentores."""
    fresh = TestClient(client.app, base_url="http://testserver")  # cookies aparte por rol
    out: dict[str, dict[str, str]] = {}
    for name, role in (
        ("admin", Role.ADMIN),
        ("staff", Role.ADMINISTRATIVO),
        ("mentor", Role.MENTOR),
        ("other", Role.MENTOR),
    ):
        out[name] = login(fresh, make_user(session_factory, role))
    return out


def ok(response: Response, status: int = 200) -> Any:
    assert response.status_code == status, f"{response.status_code}: {response.text}"
    return response.json() if response.content else None


# ---------------- salud y documentación ----------------
def test_health_and_docs(client: TestClient) -> None:
    assert ok(client.get(f"{API}/health")) == {"status": "ok"}
    assert ok(client.get(f"{API}/health/ready")) == {"status": "ok", "database": "up"}
    response = client.get(f"{API}/health")
    assert (
        response.headers["x-request-id"] and response.headers["x-content-type-options"] == "nosniff"
    )
    assert client.get("/openapi.json").status_code == 200  # solo fuera de producción
    assert (
        client.get(f"{API}/health", headers={"X-Request-ID": "mi-id-de-traza-123"}).headers[
            "x-request-id"
        ]
        == "mi-id-de-traza-123"
    )


# ---------------- autenticación ----------------
def test_login_sets_secure_cookies_and_never_returns_the_refresh_token(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    email = make_user(session_factory, Role.MENTOR)
    response = client.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD})
    body = ok(response)

    assert set(body) == {"access_token", "token_type", "expires_in", "user"}
    assert "password" not in str(body).lower() and "hash" not in str(body).lower()
    assert body["user"]["email"] == email and body["user"]["role"] == "MENTOR"
    cookies = {c.split("=", 1)[0]: c for c in response.headers.get_list("set-cookie")}
    refresh, csrf = cookies["refresh_token"], cookies["csrf_token"]
    assert "HttpOnly" in refresh and "Path=/api/v1/auth" in refresh and "SameSite=strict" in refresh
    assert "HttpOnly" not in csrf and "Path=/" in csrf  # el SPA debe poder leerla
    assert response.headers["cache-control"] == "no-store"
    raw_refresh = client.cookies.get("refresh_token")
    assert raw_refresh and raw_refresh not in response.text  # nunca en el cuerpo


def test_failed_logins_are_uniform_and_do_not_echo_secrets(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    email = make_user(session_factory, Role.MENTOR)
    wrong = client.post(f"{API}/auth/login", json={"email": email, "password": "equivocada"})
    unknown = client.post(
        f"{API}/auth/login", json={"email": "nadie@example.org", "password": PASSWORD}
    )
    for response in (wrong, unknown):
        assert response.status_code == 401
        assert response.json()["detail"] == "Credenciales inválidas"
        assert response.headers["www-authenticate"] == "Bearer"
    invalid = client.post(
        f"{API}/auth/login", json={"email": email, "password": "secreto-123", "x": 1}
    )
    assert invalid.status_code == 422
    assert "secreto-123" not in invalid.text  # los errores de validación no repiten lo enviado
    assert "input" not in invalid.json().get("errors", [{}])[0]


def test_protected_endpoints_require_a_valid_token(client: TestClient) -> None:
    assert client.get(f"{API}/auth/me").status_code == 401
    for token in ("basura", "a.b.c", ""):
        assert (
            client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code
            == 401
        )
    assert client.get(f"{API}/users").status_code == 401
    assert client.get(f"{API}/requests").status_code == 401


def test_me_returns_the_authenticated_user(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    email = make_user(session_factory, Role.ADMINISTRATIVO)
    me = ok(client.get(f"{API}/auth/me", headers=login(client, email)))
    assert me["email"] == email and me["role"] == "ADMINISTRATIVO"


def test_refresh_requires_cookie_csrf_and_rotates(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    email = make_user(session_factory, Role.MENTOR)
    login(client, email)
    cookie, csrf = client.cookies["refresh_token"], client.cookies["csrf_token"]

    assert client.post(f"{API}/auth/refresh").status_code == 403  # cookie sin cabecera CSRF
    bad = client.post(f"{API}/auth/refresh", headers={"X-CSRF-Token": "0" * 64})
    assert bad.status_code == 403
    cross_site = client.post(
        f"{API}/auth/refresh", headers={"X-CSRF-Token": csrf, "Origin": "https://evil.example"}
    )
    assert cross_site.status_code == 403  # origen no permitido
    assert client.cookies["refresh_token"] == cookie  # los intentos fallidos no rotan nada

    good = client.post(f"{API}/auth/refresh", headers={"X-CSRF-Token": csrf, "Origin": ORIGIN})
    body = ok(good)
    assert body["access_token"] and "refresh_token" not in body
    assert client.cookies["refresh_token"] != cookie  # rotación
    assert client.cookies["csrf_token"] != csrf  # el CSRF sigue ligado al token nuevo
    assert (
        client.get(
            f"{API}/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"}
        ).status_code
        == 200
    )

    # Sin cookie no hay sesión, aunque se envíe una cabecera CSRF cualquiera.
    client.cookies.clear()
    assert client.post(f"{API}/auth/refresh", headers={"X-CSRF-Token": csrf}).status_code == 401


def test_reusing_a_rotated_refresh_token_kills_the_session(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    email = make_user(session_factory, Role.MENTOR)
    login(client, email)
    old_cookie, old_csrf = client.cookies["refresh_token"], client.cookies["csrf_token"]
    fresh = ok(client.post(f"{API}/auth/refresh", headers={"X-CSRF-Token": old_csrf}))
    newest_csrf = client.cookies["csrf_token"]

    # un atacante reproduce el refresh token viejo (con su CSRF, que también conoce)
    replay = client.post(
        f"{API}/auth/refresh",
        headers={"X-CSRF-Token": old_csrf, "Cookie": f"refresh_token={old_cookie}"},
    )
    assert replay.status_code == 401
    assert any(
        "refresh_token=" in c and "Max-Age=0" in c for c in replay.headers.get_list("set-cookie")
    )
    # la sesión completa quedó revocada: ni el access token nuevo ni el refresh legítimo sirven
    assert (
        client.get(
            f"{API}/auth/me", headers={"Authorization": f"Bearer {fresh['access_token']}"}
        ).status_code
        == 401
    )
    assert (
        client.post(f"{API}/auth/refresh", headers={"X-CSRF-Token": newest_csrf}).status_code == 401
    )


def test_logout_revokes_the_session_and_clears_cookies(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    headers = login(client, make_user(session_factory, Role.MENTOR))
    response = client.post(f"{API}/auth/logout", headers=headers)
    assert response.status_code == 204
    assert client.get(f"{API}/auth/me", headers=headers).status_code == 401
    assert not client.cookies.get("refresh_token")


def test_change_password_rules_and_effect_on_other_sessions(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    email = make_user(session_factory, Role.MENTOR)
    other_device = TestClient(client.app, base_url="http://testserver")
    old = login(other_device, email)
    headers = login(client, email)
    url = f"{API}/auth/change-password"

    assert (
        client.post(
            url,
            headers=headers,
            json={"current_password": "mala", "new_password": "otra-clave-larga-9"},
        ).status_code
        == 401
    )
    weak = client.post(
        url, headers=headers, json={"current_password": PASSWORD, "new_password": "corta"}
    )
    assert weak.status_code == 422 and weak.json()["field"] == "password"
    assert (
        client.post(
            url,
            headers=headers,
            json={"current_password": PASSWORD, "new_password": "otra-clave-larga-9"},
        ).status_code
        == 204
    )
    assert (
        client.get(f"{API}/auth/me", headers=headers).status_code == 200
    )  # la sesión actual sigue
    assert other_device.get(f"{API}/auth/me", headers=old).status_code == 401  # las demás no
    login(client, email, "otra-clave-larga-9")


# ---------------- usuarios ----------------
def test_user_management_is_admin_only(
    client: TestClient, people: dict[str, dict[str, str]]
) -> None:
    for who in ("staff", "mentor"):
        assert client.get(f"{API}/users", headers=people[who]).status_code == 403
        assert client.post(f"{API}/users", headers=people[who], json={}).status_code in (403, 422)
    admin = people["admin"]
    payload = {
        "first_name": "Luis",
        "last_name": "Gómez",
        "email": "Luis@Example.org",
        "role": "MENTOR",
        "password": "clave-inicial-123",
    }
    created = ok(client.post(f"{API}/users", headers=admin, json=payload), 201)
    assert (
        created["email"] == "luis@example.org"
        and "password" not in created
        and created["is_active"]
    )

    assert (
        client.post(f"{API}/users", headers=admin, json=payload).status_code == 409
    )  # email repetido
    weak = client.post(
        f"{API}/users",
        headers=admin,
        json={**payload, "email": "otro@example.org", "password": "123"},
    )
    assert weak.status_code == 422
    assert (
        client.post(
            f"{API}/users", headers=admin, json={**payload, "role": "SUPERADMIN"}
        ).status_code
        == 422
    )

    uid = created["id"]
    assert ok(client.get(f"{API}/users/{uid}", headers=admin))["first_name"] == "Luis"
    assert (
        ok(client.patch(f"{API}/users/{uid}", headers=admin, json={"first_name": "Luis Carlos"}))[
            "first_name"
        ]
        == "Luis Carlos"
    )
    assert client.get(f"{API}/users/{uuid.uuid4()}", headers=admin).status_code == 404
    listing = ok(client.get(f"{API}/users?search=luis&page_size=5", headers=admin))
    assert listing["total"] == 1 and listing["items"][0]["id"] == uid and listing["page_size"] == 5
    assert client.get(f"{API}/users?page_size=101", headers=admin).status_code == 422
    assert client.get(f"{API}/users?page=0", headers=admin).status_code == 422


def test_deactivated_users_lose_access_immediately(
    client: TestClient, people: dict[str, dict[str, str]], session_factory: sessionmaker[Session]
) -> None:
    email = make_user(session_factory, Role.MENTOR)
    victim_headers = login(TestClient(client.app, base_url="http://testserver"), email)
    me = ok(client.get(f"{API}/auth/me", headers=victim_headers))

    off = ok(client.patch(f"{API}/users/{me['id']}/deactivate", headers=people["admin"]))
    assert off["is_active"] is False
    assert client.get(f"{API}/auth/me", headers=victim_headers).status_code == 401
    assert (
        client.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD}).status_code
        == 401
    )
    assert (
        ok(client.patch(f"{API}/users/{me['id']}/activate", headers=people["admin"]))["is_active"]
        is True
    )
    login(client, email)

    admin_id = ok(client.get(f"{API}/auth/me", headers=people["admin"]))["id"]
    assert (
        client.patch(f"{API}/users/{admin_id}/deactivate", headers=people["admin"]).status_code
        == 403
    )
    reset = client.post(
        f"{API}/users/{me['id']}/reset-password",
        headers=people["admin"],
        json={"new_password": "temporal-segura-9"},
    )
    assert reset.status_code == 204
    login(client, email, "temporal-segura-9")


# ---------------- productos y formularios ----------------
def create_product(client: TestClient, headers: dict[str, str], code: str = "LIBRO") -> int:
    product = ok(
        client.post(
            f"{API}/product-types",
            headers=headers,
            json={"code": code, "name": code.title(), "folder_name": code.title()},
        ),
        201,
    )
    return int(product["id"])


def publish_book(
    client: TestClient, headers: dict[str, str], staff: dict[str, str] | None = None
) -> tuple[int, int]:
    """Publica el libro; si se pasa `staff`, el admin le asigna el producto para que lo revise."""
    product_id = create_product(client, headers)
    versions = ok(client.get(f"{API}/product-types/{product_id}/form-versions", headers=headers))
    version_id = versions[0]["id"]
    ok(client.put(f"{API}/form-versions/{version_id}", headers=headers, json=BOOK_FORM))
    ok(client.post(f"{API}/form-versions/{version_id}/publish", headers=headers))
    if staff is not None:
        me = ok(client.get(f"{API}/auth/me", headers=staff))
        ok(
            client.put(
                f"{API}/users/{me['id']}/products",
                headers=headers,
                json={"product_type_ids": [product_id]},
            )
        )
    return product_id, version_id


def test_staff_and_admin_can_create_products_and_forms_without_touching_the_database(
    client: TestClient, people: dict[str, dict[str, str]]
) -> None:
    mentor = people["mentor"]
    for role, code in (("admin", "LIBRO"), ("staff", "PATENTE")):
        product_id = create_product(client, people[role], code)
        assert (
            client.get(f"{API}/product-types/{product_id}/form", headers=mentor).status_code == 404
        )  # sin publicar
        versions = ok(
            client.get(f"{API}/product-types/{product_id}/form-versions", headers=people[role])
        )
        vid = versions[0]["id"]
        assert (
            client.post(f"{API}/form-versions/{vid}/publish", headers=people[role]).status_code
            == 422
        )  # vacío
        saved = ok(client.put(f"{API}/form-versions/{vid}", headers=people[role], json=BOOK_FORM))
        assert [f["key"] for f in saved["sections"][0]["fields"]] == [
            "cedula",
            "titulo",
            "anio",
            "idioma",
            "isbn",
            "soporte",
        ]
        published = ok(client.post(f"{API}/form-versions/{vid}/publish", headers=people[role]))
        assert published["status"] == "PUBLICADA"
        shown = ok(client.get(f"{API}/product-types/{product_id}/form", headers=mentor))
        assert (
            shown["id"] == vid and shown["sections"][0]["fields"][3]["options"][0]["value"] == "es"
        )


def test_form_authoring_rules_over_http(
    client: TestClient, people: dict[str, dict[str, str]]
) -> None:
    admin, mentor = people["admin"], people["mentor"]
    product_id, version_id = publish_book(client, admin, people["staff"])

    assert (
        client.post(
            f"{API}/product-types", headers=mentor, json={"code": "X1", "name": "X"}
        ).status_code
        == 403
    )
    assert (
        client.put(f"{API}/form-versions/{version_id}", headers=mentor, json=BOOK_FORM).status_code
        == 403
    )
    assert client.get(f"{API}/form-versions/{version_id}", headers=mentor).status_code == 403
    assert (
        client.post(
            f"{API}/product-types", headers=admin, json={"code": "LIBRO", "name": "Otra vez"}
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"{API}/product-types", headers=admin, json={"code": "mal código", "name": "X"}
        ).status_code
        == 422
    )

    assert (
        client.put(f"{API}/form-versions/{version_id}", headers=admin, json=BOOK_FORM).status_code
        == 409
    )  # publicada: inmutable
    draft = ok(client.post(f"{API}/product-types/{product_id}/form-versions", headers=admin), 201)
    assert (
        draft["version_number"] == 2 and len(draft["sections"][0]["fields"]) == 6
    )  # copia de la publicada
    assert (
        client.post(f"{API}/product-types/{product_id}/form-versions", headers=admin).status_code
        == 409
    )  # solo un borrador

    invalid = {
        "sections": [{"title": "S", "fields": [{"key": "Mal Key", "label": "x", "type": "TEXT"}]}]
    }
    error = client.put(f"{API}/form-versions/{draft['id']}", headers=admin, json=invalid)
    assert error.status_code == 422 and error.json()["field"] == "key"
    unknown = {
        "sections": [{"title": "S", "fields": [{"key": "a", "label": "A", "type": "NO_EXISTE"}]}]
    }
    assert (
        client.put(f"{API}/form-versions/{draft['id']}", headers=admin, json=unknown).status_code
        == 422
    )
    assert (
        client.put(
            f"{API}/form-versions/{draft['id']}", headers=admin, json={"sections": [], "extra": 1}
        ).status_code
        == 422
    )

    ok(client.post(f"{API}/form-versions/{draft['id']}/publish", headers=admin))
    versions = ok(client.get(f"{API}/product-types/{product_id}/form-versions", headers=admin))
    assert [(v["version_number"], v["status"]) for v in versions] == [
        (2, "PUBLICADA"),
        (1, "RETIRADA"),
    ]

    ok(client.patch(f"{API}/product-types/{product_id}", headers=admin, json={"is_active": False}))
    assert client.get(f"{API}/product-types/{product_id}/form", headers=mentor).status_code == 404
    assert ok(client.get(f"{API}/product-types", headers=mentor))["total"] == 0
    assert ok(client.get(f"{API}/product-types", headers=admin))["total"] == 1


# ---------------- solicitudes ----------------
def test_request_lifecycle_over_http(client: TestClient, people: dict[str, dict[str, str]]) -> None:
    admin, staff, mentor, other = (people[k] for k in ("admin", "staff", "mentor", "other"))
    product_id, _ = publish_book(client, admin, people["staff"])

    created = ok(
        client.post(f"{API}/requests", headers=mentor, json={"product_type_id": product_id}), 201
    )
    rid, url = created["id"], f"{API}/requests/{created['id']}"
    assert (
        created["status"] == "BORRADOR"
        and created["request_number"].startswith("SOL-")
        and created["is_editable"]
    )
    assert created["missing_required"] == ["cedula", "titulo"] and created["form"]["sections"]

    # ownership (IDOR) y roles
    assert client.get(url, headers=other).status_code == 404
    assert client.get(url, headers=staff).status_code == 404  # borrador privado
    assert (
        client.post(
            f"{API}/requests", headers=staff, json={"product_type_id": product_id}
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"{url}/answers", headers=other, json={"version": 1, "answers": {"titulo": "x"}}
        ).status_code
        == 404
    )

    # el estado NUNCA lo envía el cliente
    assert (
        client.patch(
            f"{url}/answers",
            headers=mentor,
            json={"version": 1, "answers": {}, "status": "APROBADA"},
        ).status_code
        == 422
    )
    assert client.patch(url, headers=mentor, json={"status": "APROBADA"}).status_code == 405

    # respuestas: validación, versión optimista, todo o nada
    assert (
        client.patch(
            f"{url}/answers", headers=mentor, json={"version": 1, "answers": {"anio": 1800}}
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"{url}/answers", headers=mentor, json={"version": 1, "answers": {"nada": "x"}}
        ).status_code
        == 422
    )
    saved = ok(
        client.patch(
            f"{url}/answers",
            headers=mentor,
            json={
                "version": created["version"],
                "answers": {
                    "cedula": "1.003.895.357",
                    "titulo": " Mi libro ",
                    "anio": 2024,
                    "idioma": "es",
                },
            },
        )
    )
    assert (
        saved["answers"]
        == {"cedula": "1003895357", "titulo": "Mi libro", "anio": 2024, "idioma": "es"}
        and saved["missing_required"] == []
    )
    stale = client.patch(
        f"{url}/answers",
        headers=mentor,
        json={"version": created["version"], "answers": {"titulo": "otra pestaña"}},
    )
    assert stale.status_code == 409  # la versión ya cambió

    # ciclo: enviar -> revisar -> corrección -> reenviar -> aprobar
    sent = ok(client.post(f"{url}/submit", headers=mentor))
    assert sent["status"] == "ENVIADA" and not sent["is_editable"]
    assert (
        client.patch(
            f"{url}/answers",
            headers=mentor,
            json={"version": sent["version"], "answers": {"titulo": "x"}},
        ).status_code
        == 409
    )
    assert client.post(f"{url}/review", headers=mentor).status_code == 403
    assert client.post(f"{url}/review", headers=admin).status_code == 403  # el admin solo lee
    assert ok(client.get(url, headers=admin))["id"] == rid
    assert ok(client.post(f"{url}/review", headers=staff))["status"] == "EN_REVISION"
    assert client.post(f"{url}/approve", headers=mentor, json={}).status_code == 403
    assert (
        client.post(f"{url}/reject", headers=staff, json={}).status_code == 422
    )  # el motivo es obligatorio
    corrected = ok(
        client.post(
            f"{url}/request-correction", headers=staff, json={"description": "Falta el ISBN"}
        )
    )
    assert (
        corrected["status"] == "CORRECCION_SOLICITADA"
        and corrected["open_correction"]["description"] == "Falta el ISBN"
    )

    fixed = ok(
        client.patch(
            f"{url}/answers",
            headers=mentor,
            json={"version": corrected["version"], "answers": {"isbn": "978-0-00-000000-0"}},
        )
    )
    assert fixed["is_editable"] and fixed["answers"]["isbn"] == "978-0-00-000000-0"
    assert ok(client.post(f"{url}/resubmit", headers=mentor))["status"] == "REENVIADA"
    ok(client.post(f"{url}/review", headers=staff))
    approved = ok(client.post(f"{url}/approve", headers=staff, json={"reason": "Todo en orden"}))
    assert approved["status"] == "APROBADA" and approved["open_correction"] is None
    assert (
        client.post(f"{url}/approve", headers=staff, json={}).status_code == 409
    )  # doble aprobación

    history = ok(client.get(f"{url}/history", headers=mentor))
    assert [(h["previous_status"], h["new_status"]) for h in history] == [
        (None, "BORRADOR"), ("BORRADOR", "ENVIADA"), ("ENVIADA", "EN_REVISION"),
        ("EN_REVISION", "CORRECCION_SOLICITADA"), ("CORRECCION_SOLICITADA", "REENVIADA"),
        ("REENVIADA", "EN_REVISION"), ("EN_REVISION", "APROBADA"),
    ]  # fmt: skip
    assert client.get(f"{url}/history", headers=other).status_code == 404
    (correction,) = ok(client.get(f"{url}/corrections", headers=staff))
    assert correction["status"] == "RESUELTA" and correction["resolved_at"]


def test_incomplete_requests_report_the_missing_fields(
    client: TestClient, people: dict[str, dict[str, str]]
) -> None:
    product_id, _ = publish_book(client, people["admin"], people["staff"])
    mentor = people["mentor"]
    rid = ok(
        client.post(f"{API}/requests", headers=mentor, json={"product_type_id": product_id}), 201
    )["id"]
    response = client.post(f"{API}/requests/{rid}/submit", headers=mentor)
    assert response.status_code == 422
    assert (
        response.json()["missing"] == ["cedula", "titulo"]
        and response.json()["code"] == "IncompleteProduct"
    )
    assert ok(client.get(f"{API}/requests/{rid}", headers=mentor))["status"] == "BORRADOR"


def test_listing_scope_filters_and_pagination_over_http(
    client: TestClient, people: dict[str, dict[str, str]]
) -> None:
    admin, staff, mentor, other = (people[k] for k in ("admin", "staff", "mentor", "other"))
    product_id, _ = publish_book(client, admin, people["staff"])

    def new(headers: dict[str, str], title: str | None) -> dict[str, Any]:
        created = ok(
            client.post(f"{API}/requests", headers=headers, json={"product_type_id": product_id}),
            201,
        )
        if title:
            ok(
                client.patch(
                    f"{API}/requests/{created['id']}/answers",
                    headers=headers,
                    json={
                        "version": created["version"],
                        "answers": {"cedula": "1003895357", "titulo": title},
                    },
                )
            )
            ok(client.post(f"{API}/requests/{created['id']}/submit", headers=headers))
        return dict(created)

    draft, sent, foreign = new(mentor, None), new(mentor, "Enviada"), new(other, "Ajena")

    mine = ok(client.get(f"{API}/requests", headers=mentor))
    assert mine["total"] == 2 and {i["id"] for i in mine["items"]} == {draft["id"], sent["id"]}
    spoof = ok(
        client.get(
            f"{API}/requests?mentor_id={ok(client.get(f'{API}/auth/me', headers=other))['id']}",
            headers=mentor,
        )
    )
    assert spoof["total"] == 2  # un mentor no puede ver las de otro pidiéndolas
    for viewer in (staff, admin):
        page = ok(client.get(f"{API}/requests?page_size=1", headers=viewer))
        assert page["total"] == 2 and page["total_pages"] == 2 and len(page["items"]) == 1
        assert draft["id"] not in str(
            ok(client.get(f"{API}/requests?page_size=50", headers=viewer))
        )
    assert (
        ok(
            client.get(
                f"{API}/requests?status=ENVIADA&request_number={sent['request_number']}",
                headers=staff,
            )
        )["total"]
        == 1
    )
    assert ok(client.get(f"{API}/requests?status=APROBADA", headers=staff))["total"] == 0
    assert (
        ok(client.get(f"{API}/requests?product_type_id={product_id}", headers=staff))["total"] == 2
    )
    row = ok(
        client.get(f"{API}/requests?request_number={foreign['request_number']}", headers=staff)
    )["items"][0]
    assert (
        row["mentor"]["name"] and row["product_type_code"] == "LIBRO" and row["status"] == "ENVIADA"
    )
    assert client.get(f"{API}/requests?status=INVENTADO", headers=staff).status_code == 422
    assert client.get(f"{API}/requests?page_size=500", headers=staff).status_code == 422


# ---------------- CORS y errores ----------------
def test_cors_allows_only_configured_origins(client: TestClient) -> None:
    preflight = client.options(
        f"{API}/auth/login",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-csrf-token,content-type",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == ORIGIN
    assert preflight.headers["access-control-allow-credentials"] == "true"
    denied = client.options(
        f"{API}/auth/login",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in denied.headers


def test_unexpected_errors_never_leak_internals(client: TestClient) -> None:
    assert client.get(
        f"{API}/requests/no-es-un-uuid", headers={"Authorization": "Bearer x"}
    ).status_code in (401, 422)
    response = client.get(f"{API}/no-existe")
    assert response.status_code == 404 and "Traceback" not in response.text
