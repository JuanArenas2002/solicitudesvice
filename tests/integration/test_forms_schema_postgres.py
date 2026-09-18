"""Integridad de formularios y respuestas tipadas contra PostgreSQL REAL.

Aquí se prueba que la BASE DE DATOS (FK compuestos, CHECK e índices parciales) garantiza por sí
sola la coherencia entre solicitud, versión de formulario, campo, tipo y valor de cada respuesta.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.enums.form_status import FormStatus as F
from app.domain.enums.request_status import RequestStatus
from app.domain.enums.role import Role
from app.domain.forms.field_types import FIELD_TYPES
from app.infrastructure.database.catalog import (
    FIELD_TYPE_IDS,
    FORM_STATUS_IDS,
    REQUEST_STATUS_IDS,
    ROLE_IDS,
    VALUE_KIND_IDS,
)
from app.infrastructure.database.models import (
    FormFieldModel,
    FormFieldOptionModel,
    FormSectionModel,
    FormVersionModel,
    ProductTypeModel,
    RequestAnswerModel,
    ResearchProductRequestModel,
    UserModel,
)

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)


def flush(session: Session, *rows: object) -> None:
    session.add_all(rows)
    session.flush()


@dataclass
class Ctx:
    """Un producto con su formulario publicado (v1), un borrador (v2) y una solicitud sobre v1."""

    session: Session
    product: ProductTypeModel
    v1: FormVersionModel
    v2: FormVersionModel
    section: FormSectionModel
    fields: dict[str, FormFieldModel]
    options: dict[str, FormFieldOptionModel]
    other_field: FormFieldModel  # campo de la v2
    request: ResearchProductRequestModel

    def answer(self, key: str, **values: object) -> RequestAnswerModel:
        f = self.fields[key]
        code = next(c for c, i in FIELD_TYPE_IDS.items() if i == f.field_type_id)
        data: dict[str, object] = {
            "request_id": self.request.id,
            "form_version_id": self.v1.id,
            "field_id": f.id,
            "field_type_id": f.field_type_id,
            "value_kind_id": VALUE_KIND_IDS[FIELD_TYPES[code].kind],
        }
        return RequestAnswerModel(**{**data, **values})


def build(session: Session) -> Ctx:
    product = ProductTypeModel(
        code=f"P{uuid.uuid4().hex[:8].upper()}", name="Producto", folder_name="Producto"
    )
    session.add(product)
    session.flush()
    v1 = FormVersionModel(
        product_type_id=product.id,
        version_number=1,
        status_id=FORM_STATUS_IDS[F.PUBLICADA],
        published_at=NOW,
    )
    v2 = FormVersionModel(
        product_type_id=product.id, version_number=2, status_id=FORM_STATUS_IDS[F.BORRADOR]
    )
    flush(session, v1, v2)
    section = FormSectionModel(form_version_id=v1.id, position=1, title="Datos")
    section2 = FormSectionModel(form_version_id=v2.id, position=1, title="Datos v2")
    flush(session, section, section2)

    specs = [
        ("titulo", "TEXT"),
        ("anio", "INTEGER"),
        ("doi", "DOI"),
        ("url", "URL"),
        ("issn", "ISSN"),
        ("mail", "EMAIL"),
        ("fecha", "DATE"),
        ("ok", "BOOLEAN"),
        ("idioma", "SINGLE_SELECT"),
        ("etiquetas", "MULTI_SELECT"),
        ("largo", "LONG_TEXT"),
        ("importe", "DECIMAL"),
    ]
    fields = {
        key: FormFieldModel(
            form_version_id=v1.id,
            section_id=section.id,
            position=i,
            key=key,
            label=key.title(),
            field_type_id=FIELD_TYPE_IDS[code],
        )
        for i, (key, code) in enumerate(specs, start=1)
    }
    other = FormFieldModel(
        form_version_id=v2.id,
        section_id=section2.id,
        position=1,
        key="otro",
        label="Otro",
        field_type_id=FIELD_TYPE_IDS["TEXT"],
    )
    flush(session, *fields.values(), other)
    options = {
        "es": FormFieldOptionModel(
            field_id=fields["idioma"].id, position=1, value="es", label="ES"
        ),
        "en": FormFieldOptionModel(
            field_id=fields["idioma"].id, position=2, value="en", label="EN"
        ),
        "a": FormFieldOptionModel(
            field_id=fields["etiquetas"].id, position=1, value="a", label="A"
        ),
        "b": FormFieldOptionModel(
            field_id=fields["etiquetas"].id, position=2, value="b", label="B"
        ),
    }
    flush(session, *options.values())

    mentor = UserModel(
        id=uuid.uuid4(),
        first_name="Ana",
        last_name="Pérez",
        email=f"{uuid.uuid4().hex}@example.org",
        password_hash="$argon2id$x",
        role_id=ROLE_IDS[Role.MENTOR],
    )
    flush(session, mentor)
    request = ResearchProductRequestModel(
        id=uuid.uuid4(),
        request_number=f"SOL-2026-{uuid.uuid4().int % 999999 + 1:06d}",
        mentor_id=mentor.id,
        form_version_id=v1.id,
        status_id=REQUEST_STATUS_IDS[RequestStatus.BORRADOR],
    )
    flush(session, request)
    return Ctx(session, product, v1, v2, section, fields, options, other, request)


# ---------------- respuestas válidas ----------------
def test_typed_answers_of_every_kind_are_accepted(engine: Engine) -> None:
    with Session(engine) as session:
        c = build(session)
        flush(
            session,
            c.answer("titulo", value_text="Un estudio"),
            c.answer("anio", value_number=Decimal(2025)),
            c.answer("doi", value_text="10.1234/abc.1"),
            c.answer("url", value_text="https://example.org/a"),
            c.answer("issn", value_text="1234-567X"),
            c.answer("mail", value_text="ana@example.org"),
            c.answer("fecha", value_date=date(2025, 3, 14)),
            c.answer("ok", value_boolean=False),  # False es un valor, no "vacío"
            c.answer("importe", value_number=Decimal("12.345600")),
            c.answer("largo", value_text="x" * 10_000),
            c.answer("idioma", option_id=c.options["es"].id),
            c.answer("etiquetas", option_id=c.options["a"].id),
            c.answer(
                "etiquetas", option_id=c.options["b"].id
            ),  # multi-selección: una fila por opción
        )
        session.rollback()


# ---------------- respuestas que la BD debe rechazar ----------------
def _other_version_field(c: Ctx) -> RequestAnswerModel:
    """Campo de OTRA versión respondido en una solicitud de la v1."""
    other = c.other_field
    return RequestAnswerModel(
        request_id=c.request.id,
        form_version_id=c.v1.id,
        field_id=other.id,
        field_type_id=other.field_type_id,
        value_kind_id=VALUE_KIND_IDS[FIELD_TYPES["TEXT"].kind],
        value_text="x",
    )


REJECTED: dict[str, Callable[[Ctx], list[RequestAnswerModel]]] = {
    "valor en la columna equivocada (texto en un campo numérico)": lambda c: [
        c.answer("anio", value_text="2025")
    ],
    "dos valores en la misma fila": lambda c: [
        c.answer("titulo", value_text="x", value_number=Decimal(1))
    ],
    "sin ningún valor": lambda c: [c.answer("titulo")],
    "campo de otra versión": lambda c: [_other_version_field(c)],
    "tipo declarado distinto al del campo": lambda c: [
        c.answer("titulo", value_text="x", field_type_id=FIELD_TYPE_IDS["DOI"])
    ],
    "clase de valor que no corresponde al tipo": lambda c: [
        c.answer(
            "titulo",
            value_number=Decimal(5),
            value_kind_id=VALUE_KIND_IDS[FIELD_TYPES["INTEGER"].kind],
        )
    ],
    "versión declarada distinta a la de la solicitud": lambda c: [
        c.answer("titulo", value_text="x", form_version_id=c.v2.id)
    ],
    "opción de otro campo": lambda c: [c.answer("etiquetas", option_id=c.options["es"].id)],
    "dos respuestas al mismo campo": lambda c: [
        c.answer("titulo", value_text="a"),
        c.answer("titulo", value_text="b"),
    ],
    "dos opciones en una selección única": lambda c: [
        c.answer("idioma", option_id=c.options["es"].id),
        c.answer("idioma", option_id=c.options["en"].id),
    ],
    "la misma opción repetida en multi-selección": lambda c: [
        c.answer("etiquetas", option_id=c.options["a"].id),
        c.answer("etiquetas", option_id=c.options["a"].id),
    ],
    "DOI mal formado": lambda c: [c.answer("doi", value_text="no-es-doi")],
    "ISSN mal formado": lambda c: [c.answer("issn", value_text="12345678")],
    "URL mal formada": lambda c: [c.answer("url", value_text="ftp://x.org")],
    "email con mayúsculas": lambda c: [c.answer("mail", value_text="Ana@Example.org")],
    "email mal formado": lambda c: [c.answer("mail", value_text="sin-arroba")],
    "entero con decimales": lambda c: [c.answer("anio", value_number=Decimal("2025.5"))],
    "texto en blanco": lambda c: [c.answer("titulo", value_text="   ")],
    "texto demasiado largo": lambda c: [c.answer("largo", value_text="x" * 10_001)],
}


@pytest.mark.parametrize("case", list(REJECTED))
def test_database_rejects_inconsistent_answers(engine: Engine, case: str) -> None:
    with Session(engine) as session:
        ctx = build(session)
        with pytest.raises(IntegrityError):
            flush(session, *REJECTED[case](ctx))


def test_answers_cannot_reference_a_missing_request_or_field(engine: Engine) -> None:
    with Session(engine) as session:
        c = build(session)
        with pytest.raises(IntegrityError):
            flush(session, c.answer("titulo", value_text="x", request_id=uuid.uuid4()))
    with Session(engine) as session:
        c = build(session)
        with pytest.raises(IntegrityError):
            flush(session, c.answer("titulo", value_text="x", field_id=999_999))


def test_a_form_field_in_use_cannot_be_deleted(engine: Engine) -> None:
    with Session(engine) as session:
        c = build(session)
        flush(session, c.answer("titulo", value_text="x"))
        session.delete(c.fields["titulo"])
        with pytest.raises(IntegrityError):
            session.flush()


# ---------------- estructura de formularios ----------------
def _second_published(c: Ctx) -> None:
    flush(
        c.session,
        FormVersionModel(
            product_type_id=c.product.id,
            version_number=9,
            status_id=FORM_STATUS_IDS[F.PUBLICADA],
            published_at=NOW,
        ),
    )


def _version(c: Ctx, number: int, status: F, **dates: object) -> None:
    flush(
        c.session,
        FormVersionModel(
            product_type_id=c.product.id,
            version_number=number,
            status_id=FORM_STATUS_IDS[status],
            **dates,
        ),
    )


def _field(c: Ctx, **overrides: object) -> None:
    data: dict[str, object] = {
        "form_version_id": c.v1.id,
        "section_id": c.section.id,
        "position": 99,
        "key": "nuevo",
        "label": "Nuevo",
        "field_type_id": FIELD_TYPE_IDS["TEXT"],
    }
    flush(c.session, FormFieldModel(**{**data, **overrides}))


STRUCTURE_REJECTED: dict[str, Callable[[Ctx], None]] = {
    "dos versiones publicadas del mismo producto": _second_published,
    "dos borradores del mismo producto": lambda c: _version(c, 8, F.BORRADOR),
    "número de versión repetido": lambda c: _version(
        c, 1, F.RETIRADA, published_at=NOW, retired_at=NOW
    ),
    "versión 0": lambda c: _version(c, 0, F.RETIRADA, published_at=NOW, retired_at=NOW),
    "publicada sin fecha de publicación": lambda c: _version(c, 7, F.PUBLICADA),
    "borrador con fecha de publicación": lambda c: c.session.add(
        FormVersionModel(
            product_type_id=c.product.id, version_number=6, status_id=1, published_at=NOW
        )
    ),
    "retirada antes de publicarse": lambda c: _version(
        c, 5, F.RETIRADA, published_at=NOW, retired_at=NOW.replace(year=2020)
    ),
    "campo con sección de otra versión": lambda c: _field(c, form_version_id=c.v2.id),
    "clave de campo repetida en la versión": lambda c: _field(c, key="titulo"),
    "clave con formato inválido": lambda c: _field(c, key="Clave Mala"),
    "posición de campo repetida": lambda c: _field(c, position=1),
    "tipo de campo inexistente": lambda c: _field(c, field_type_id=999),
    "longitud mínima mayor que la máxima": lambda c: _field(c, min_length=10, max_length=2),
    "rango de valores invertido": lambda c: _field(c, min_value=Decimal(10), max_value=Decimal(1)),
    "etiqueta en blanco": lambda c: _field(c, label="   "),
    "opción repetida en el campo": lambda c: flush(
        c.session,
        FormFieldOptionModel(field_id=c.fields["idioma"].id, position=5, value="es", label="X"),
    ),
    "opción en blanco": lambda c: flush(
        c.session,
        FormFieldOptionModel(field_id=c.fields["idioma"].id, position=6, value=" ", label="X"),
    ),
    "código de producto en minúsculas": lambda c: flush(
        c.session, ProductTypeModel(code="libro", name="Libro", folder_name="Libro")
    ),
    "código de producto repetido": lambda c: flush(
        c.session, ProductTypeModel(code=c.product.code, name="Otro", folder_name="Otro")
    ),
    "sección sin título": lambda c: flush(
        c.session, FormSectionModel(form_version_id=c.v1.id, position=7, title="  ")
    ),
}


@pytest.mark.parametrize("case", list(STRUCTURE_REJECTED))
def test_database_rejects_invalid_form_structure(engine: Engine, case: str) -> None:
    with Session(engine) as session:
        ctx = build(session)
        with pytest.raises(IntegrityError):
            STRUCTURE_REJECTED[case](ctx)
            session.flush()
            session.commit()  # las restricciones diferidas (posiciones) se validan al confirmar


def test_same_key_can_exist_in_different_versions(engine: Engine) -> None:
    with Session(engine) as session:
        c = build(session)
        flush(
            session,
            FormFieldModel(
                form_version_id=c.v2.id,
                section_id=c.other_field.section_id,
                position=2,
                key="titulo",  # también existe en la v1
                label="Título",
                field_type_id=FIELD_TYPE_IDS["TEXT"],
            ),
        )
        session.rollback()


def test_positions_can_be_swapped_within_a_transaction(engine: Engine) -> None:
    with Session(engine) as session:
        c = build(session)
        a, b = c.fields["titulo"], c.fields["anio"]
        a.position, b.position = b.position, a.position  # restricción diferida: válido al commit
        session.flush()
        session.commit()
        c.fields["doi"].position = a.position  # ahora sí choca
        with pytest.raises(IntegrityError):
            session.commit()


def test_form_structure_referenced_by_answers_cannot_be_deleted(engine: Engine) -> None:
    with Session(engine) as session:
        c = build(session)
        flush(session, c.answer("titulo", value_text="x"))
        session.delete(c.section)  # el ORM borra sus campos, pero una respuesta los referencia
        with pytest.raises(IntegrityError):
            session.flush()
