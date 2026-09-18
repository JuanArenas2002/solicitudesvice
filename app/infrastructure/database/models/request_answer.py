import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    Uuid,
    and_,
    column,
    func,
    or_,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.expression import ColumnClause, ColumnElement

from app.domain.enums.value_kind import ValueKind as K
from app.domain.forms import field_types as ft
from app.domain.forms.field_types import LONG_TEXT_MAX_LENGTH
from app.domain.value_objects.identifiers import (
    CEDULA_PATTERN,
    DOI_PATTERN,
    ISSN_PATTERN,
    URL_PATTERN,
)
from app.infrastructure.database.base import Base
from app.infrastructure.database.catalog import FIELD_TYPE_IDS, VALUE_KIND_IDS

_kind: ColumnClause[int] = column("value_kind_id")
_type: ColumnClause[int] = column("field_type_id")
_text: ColumnClause[str] = column("value_text")
_number: ColumnClause[Decimal] = column("value_number")
_date: ColumnClause[date] = column("value_date")
_bool: ColumnClause[bool] = column("value_boolean")
_option: ColumnClause[int] = column("option_id")
_VALUES: dict[str, ColumnClause[Any]] = {
    "text": _text,
    "number": _number,
    "date": _date,
    "boolean": _bool,
    "option": _option,
}

# Regex de correo apto para PostgreSQL (sin barras invertidas); ademas se exige minuscula.
EMAIL_DB_PATTERN = "^[^@ ]+@[^@ ]+[.][^@ ]+$"


def _only(kept: str) -> ColumnElement[bool]:
    """Exactamente esa columna de valor con dato y todas las demas vacias."""
    return and_(*(c.is_not(None) if name == kept else c.is_(None) for name, c in _VALUES.items()))


def _format_check(type_code: str, condition: ColumnElement[bool]) -> ColumnElement[bool]:
    """Si la respuesta es de ese tipo de campo debe cumplir el formato; otros tipos no se tocan."""
    return or_(_type != FIELD_TYPE_IDS[type_code], condition)


class RequestAnswerModel(Base):
    """Respuesta tipada a un campo del formulario (multi-selección = una fila por opción).

    Los FK compuestos hacen que LA BASE DE DATOS garantice que la respuesta pertenece a la versión
    de formulario de su solicitud, que el tipo declarado es el del campo, que el tipo de valor
    corresponde al tipo de campo y que la opción elegida pertenece al campo.
    """

    __tablename__ = "request_answers"
    __table_args__ = (
        ForeignKeyConstraint(
            ["request_id", "form_version_id"],
            ["research_product_requests.id", "research_product_requests.form_version_id"],
            name="fk_request_answers_request_id_research_product_requests",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["field_id", "form_version_id", "field_type_id"],
            ["form_fields.id", "form_fields.form_version_id", "form_fields.field_type_id"],
            name="fk_request_answers_field_id_form_fields",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["field_type_id", "value_kind_id"],
            ["field_types.id", "field_types.value_kind_id"],
            name="fk_request_answers_field_type_id_field_types",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["option_id", "field_id"],
            ["form_field_options.id", "form_field_options.field_id"],
            name="fk_request_answers_option_id_form_field_options",
            ondelete="RESTRICT",
        ),
        # Cada respuesta llena únicamente la columna que corresponde a la clase de valor del campo.
        CheckConstraint(
            or_(
                and_(_kind == VALUE_KIND_IDS[K.TEXT], _only("text")),
                and_(_kind == VALUE_KIND_IDS[K.NUMBER], _only("number")),
                and_(_kind == VALUE_KIND_IDS[K.DATE], _only("date")),
                and_(_kind == VALUE_KIND_IDS[K.BOOLEAN], _only("boolean")),
                and_(_kind == VALUE_KIND_IDS[K.OPTION], _only("option")),
            ),
            name="value_matches_kind",
        ),
        CheckConstraint(func.length(func.trim(_text)) > 0, name="text_not_blank"),
        CheckConstraint(func.length(_text) <= LONG_TEXT_MAX_LENGTH, name="text_max_length"),
        CheckConstraint(_format_check(ft.DOI, _text.regexp_match(DOI_PATTERN)), name="doi_format"),
        CheckConstraint(
            _format_check(ft.ISSN, _text.regexp_match(ISSN_PATTERN)), name="issn_format"
        ),
        CheckConstraint(_format_check(ft.URL, _text.regexp_match(URL_PATTERN)), name="url_format"),
        CheckConstraint(
            _format_check(
                ft.EMAIL, and_(_text.regexp_match(EMAIL_DB_PATTERN), _text == func.lower(_text))
            ),
            name="email_format",
        ),
        CheckConstraint(
            _format_check(ft.INTEGER, func.trunc(_number) == _number),
            name="integer_is_whole",
        ),
        CheckConstraint(
            _format_check(ft.CEDULA, _text.regexp_match(CEDULA_PATTERN)), name="cedula_format"
        ),
        Index("ix_request_answers_request_id", "request_id"),
        # Una respuesta por campo; en multi-selección, una fila por opción elegida (sin repetir).
        Index(
            "uq_request_answers_single",
            "request_id",
            "field_id",
            unique=True,
            postgresql_where=_option.is_(None),
        ),
        Index(
            "uq_request_answers_option",
            "request_id",
            "field_id",
            "option_id",
            unique=True,
            postgresql_where=_option.is_not(None),
        ),
        # La selección única admite una sola opción por campo.
        Index(
            "uq_request_answers_single_select",
            "request_id",
            "field_id",
            unique=True,
            postgresql_where=_type == FIELD_TYPE_IDS[ft.SINGLE_SELECT],
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    request_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    form_version_id: Mapped[int] = mapped_column(Integer)
    field_id: Mapped[int] = mapped_column(Integer)
    field_type_id: Mapped[int] = mapped_column(SmallInteger)
    value_kind_id: Mapped[int] = mapped_column(SmallInteger)
    value_text: Mapped[str | None] = mapped_column(Text)
    value_number: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    value_date: Mapped[date | None] = mapped_column(Date)
    value_boolean: Mapped[bool | None] = mapped_column(Boolean)
    option_id: Mapped[int | None] = mapped_column(Integer)
