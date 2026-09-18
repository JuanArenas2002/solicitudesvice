"""Integridad del esquema contra un PostgreSQL REAL (TEST_DATABASE_URL, base de datos vacía).

Comprueba que la migración sube/baja, que coincide con los modelos, que los catálogos quedan
sembrados y que la BASE DE DATOS (no solo Python) rechaza los datos inválidos.
Sin PostgreSQL estos tests se saltan (ver conftest).
"""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Engine, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.domain.enums.correction_status import CorrectionStatus as C
from app.domain.enums.form_status import FormStatus
from app.domain.enums.request_status import RequestStatus as S
from app.domain.enums.role import Role
from app.infrastructure.database.catalog import (
    CORRECTION_STATUS_IDS,
    FORM_STATUS_IDS,
    REQUEST_STATUS_IDS,
    ROLE_IDS,
    lookup_rows,
)
from app.infrastructure.database.models import (
    AuditActionModel,
    AuditCategoryModel,
    AuditLogModel,
    AuthSessionModel,
    Base,
    CorrectionStatusModel,
    DocumentTypeModel,
    FieldTypeModel,
    FormStatusModel,
    FormVersionModel,
    ProductTypeModel,
    RefreshTokenModel,
    RequestCorrectionModel,
    RequestCounterModel,
    RequestStatusHistoryModel,
    RequestStatusModel,
    ResearchProductRequestModel,
    RoleModel,
    UserModel,
    ValueKindModel,
)
from tests.integration.support import alembic_config

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)


def status_id(status: S) -> int:
    return REQUEST_STATUS_IDS[status]


def test_migration_matches_models(engine: Engine) -> None:
    with engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        assert compare_metadata(context, Base.metadata) == []


def test_downgrade_and_upgrade_roundtrip(engine: Engine) -> None:
    config = alembic_config()
    command.downgrade(config, "base")
    assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
    command.upgrade(config, "head")
    assert set(Base.metadata.tables) <= set(inspect(engine).get_table_names())


def test_lookup_tables_are_seeded_exactly_like_the_catalog(engine: Engine) -> None:
    def rows(model: Any, *columns: str) -> list[tuple[object, ...]]:
        with Session(engine) as session:
            return [tuple(getattr(r, c) for c in columns) for r in session.scalars(select(model))]

    actual = {
        "roles": rows(RoleModel, "id", "code"),
        "request_statuses": rows(RequestStatusModel, "id", "code"),
        "correction_statuses": rows(CorrectionStatusModel, "id", "code"),
        "form_statuses": rows(FormStatusModel, "id", "code"),
        "value_kinds": rows(ValueKindModel, "id", "code"),
        "document_types": rows(DocumentTypeModel, "id", "code"),
        "field_types": rows(FieldTypeModel, "id", "code", "value_kind_id"),
        "audit_categories": rows(AuditCategoryModel, "id", "code"),
        "audit_actions": rows(AuditActionModel, "id", "code", "category_id", "entity_type"),
    }
    for table, expected in lookup_rows().items():
        assert sorted(actual[table], key=str) == sorted(expected, key=str), table


# ---------- fábricas de filas ----------
def user(**overrides: object) -> UserModel:
    data: dict[str, object] = {
        "id": uuid.uuid4(),
        "first_name": "Ana",
        "last_name": "Pérez",
        "email": f"{uuid.uuid4().hex}@example.org",
        "password_hash": "$argon2id$x",
        "role_id": ROLE_IDS[Role.MENTOR],
    }
    return UserModel(**{**data, **overrides})


def product_and_form(session: Session) -> FormVersionModel:
    """Un producto con su formulario publicado (las solicitudes necesitan una versión real)."""
    product = ProductTypeModel(
        code=f"P{uuid.uuid4().hex[:8].upper()}", name="Producto", folder_name="Producto"
    )
    session.add(product)
    session.flush()
    version = FormVersionModel(
        product_type_id=product.id,
        version_number=1,
        status_id=FORM_STATUS_IDS[FormStatus.PUBLICADA],
        published_at=NOW,
    )
    session.add(version)
    session.flush()
    return version


def request_row(
    mentor_id: uuid.UUID, form_version_id: int, **overrides: object
) -> ResearchProductRequestModel:
    data: dict[str, object] = {
        "id": uuid.uuid4(),
        "request_number": f"SOL-2026-{uuid.uuid4().int % 999999 + 1:06d}",
        "mentor_id": mentor_id,
        "form_version_id": form_version_id,
        "status_id": status_id(S.BORRADOR),
    }
    return ResearchProductRequestModel(**{**data, **overrides})


def _flush(session: Session, *rows: object) -> None:
    session.add_all(rows)
    session.flush()


def _valid_request(session: Session) -> tuple[UserModel, ResearchProductRequestModel]:
    version = product_and_form(session)
    mentor = user()
    _flush(session, mentor)
    row = request_row(mentor.id, version.id)
    _flush(session, row)
    return mentor, row


def _with_request(session: Session, **overrides: object) -> None:
    version = product_and_form(session)
    mentor = user()
    _flush(session, mentor)
    _flush(session, request_row(mentor.id, version.id, **overrides))


def _with_reviewed_request(session: Session, **overrides: object) -> None:
    version = product_and_form(session)
    mentor = user()
    _flush(session, mentor)
    _flush(
        session,
        request_row(mentor.id, version.id, submitted_at=NOW, reviewer_id=mentor.id, **overrides),
    )


# ---------- el motor rechaza datos inválidos ----------
def test_valid_rows_are_accepted(engine: Engine) -> None:
    with Session(engine) as session:
        _valid_request(session)
        session.rollback()


REJECTED: dict[str, Callable[[Session], None]] = {
    "email duplicado": lambda s: _flush(
        s, user(email="dup@example.org"), user(email="dup@example.org")
    ),
    "email con mayúsculas": lambda s: _flush(s, user(email="Ana@Example.org")),
    "rol inexistente (FK a catálogo)": lambda s: _flush(s, user(role_id=99)),
    "nombre en blanco": lambda s: _flush(s, user(first_name="   ")),
    "borrador con submitted_at": lambda s: _with_request(s, submitted_at=NOW),
    "enviada sin submitted_at": lambda s: _with_request(s, status_id=status_id(S.ENVIADA)),
    "en revisión sin revisor": lambda s: _with_request(
        s, status_id=status_id(S.EN_REVISION), submitted_at=NOW
    ),
    "enviada con revisor": lambda s: _with_reviewed_request(s, status_id=status_id(S.ENVIADA)),
    "aprobada sin reviewed_at": lambda s: _with_reviewed_request(
        s, status_id=status_id(S.APROBADA)
    ),
    "estado inexistente (FK a catálogo)": lambda s: _with_request(s, status_id=99),
    "formulario inexistente (FK)": lambda s: _flush(
        s, user(id=(u := uuid.uuid4())), request_row(u, 999_999)
    ),
    "número de solicitud mal formado": lambda s: _with_request(s, request_number="SOL-26-1"),
    "contador fuera de rango": lambda s: _flush(s, RequestCounterModel(year=2026, last_value=-1)),
    "auditoría con acción inexistente": lambda s: _flush(
        s, AuditLogModel(action_id=999, detail={})
    ),
}


@pytest.mark.parametrize("case", list(REJECTED))
def test_database_rejects_invalid_data(engine: Engine, case: str) -> None:
    with Session(engine) as session, pytest.raises(IntegrityError):
        REJECTED[case](session)


def test_duplicate_request_number_is_rejected(engine: Engine) -> None:
    with Session(engine) as session, pytest.raises(IntegrityError):
        mentor, first = _valid_request(session)
        _flush(
            session,
            request_row(mentor.id, first.form_version_id, request_number=first.request_number),
        )


def test_audit_log_accepts_valid_entries_with_inet_address(engine: Engine) -> None:
    with Session(engine) as session:
        _flush(session, AuditLogModel(action_id=2, detail={"reason": "bad_password"}))
        _flush(session, AuditLogModel(action_id=2, ip_address="192.168.1.10", detail={}))
        with pytest.raises(Exception, match="inet"):  # tipo inet: rechaza direcciones inválidas
            _flush(session, AuditLogModel(action_id=2, ip_address="no-es-ip", detail={}))


def test_refresh_token_hash_must_be_sha256(engine: Engine) -> None:
    with Session(engine) as session:
        mentor = user()
        auth = AuthSessionModel(id=uuid.uuid4(), user_id=mentor.id, expires_at=NOW)
        _flush(session, mentor)
        _flush(session, auth)
        with pytest.raises(IntegrityError):
            _flush(
                session,
                RefreshTokenModel(
                    id=uuid.uuid4(), session_id=auth.id, token_hash="x", expires_at=NOW
                ),
            )


def test_only_one_open_correction_per_request(engine: Engine) -> None:
    with Session(engine) as session:
        mentor, row = _valid_request(session)

        def correction(status: C, resolved: datetime | None) -> RequestCorrectionModel:
            return RequestCorrectionModel(
                id=uuid.uuid4(),
                request_id=row.id,
                requested_by=mentor.id,
                description="Corregir",
                status_id=CORRECTION_STATUS_IDS[status],
                resolved_at=resolved,
            )

        # Una abierta y una resuelta conviven; una segunda abierta la rechaza la BD.
        _flush(session, correction(C.ABIERTA, None), correction(C.RESUELTA, NOW))
        with pytest.raises(IntegrityError):
            _flush(session, correction(C.ABIERTA, None))


def test_status_history_rules(engine: Engine) -> None:
    def entry(
        request_id: uuid.UUID, by: uuid.UUID, previous: S | None, new: S
    ) -> RequestStatusHistoryModel:
        return RequestStatusHistoryModel(
            request_id=request_id,
            previous_status_id=status_id(previous) if previous else None,
            new_status_id=status_id(new),
            changed_by=by,
        )

    with Session(engine) as session:
        mentor, row = _valid_request(session)
        _flush(session, entry(row.id, mentor.id, None, S.BORRADOR))
        with pytest.raises(IntegrityError):
            _flush(session, entry(row.id, mentor.id, None, S.ENVIADA))  # crear siempre en borrador
    with Session(engine) as session:
        mentor, row = _valid_request(session)
        with pytest.raises(IntegrityError):
            _flush(session, entry(row.id, mentor.id, S.ENVIADA, S.ENVIADA))  # debe cambiar


def test_users_cannot_be_physically_deleted_while_referenced(engine: Engine) -> None:
    with Session(engine) as session:
        mentor, _ = _valid_request(session)
        session.delete(mentor)
        with pytest.raises(IntegrityError):
            session.flush()


def test_optimistic_locking_detects_concurrent_updates(engine: Engine) -> None:
    with Session(engine) as setup:
        mentor, row = _valid_request(setup)
        setup.commit()
        request_id = row.id
    with Session(engine) as first, Session(engine) as second:
        a = first.get(ResearchProductRequestModel, request_id)
        b = second.get(ResearchProductRequestModel, request_id)
        assert a is not None and b is not None and a.version == b.version == 1
        a.updated_at = NOW
        first.commit()
        b.updated_at = NOW.replace(hour=15)
        with pytest.raises(StaleDataError):
            second.commit()
