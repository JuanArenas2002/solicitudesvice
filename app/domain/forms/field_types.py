"""Tipos de campo disponibles para los formularios.

Cada tipo es una entrada de FIELD_TYPES: cómo validar y normalizar una respuesta y en qué columna
tipada de `request_answers` se guarda (ValueKind). Agregar un tipo nuevo = registrar una entrada
aquí + una fila en el catálogo `field_types`. Usar los tipos existentes en formularios nuevos no
requiere ningún cambio de código ni de base de datos.
"""

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from types import MappingProxyType

from app.domain.enums.value_kind import ValueKind
from app.domain.exceptions.errors import InvalidValue
from app.domain.value_objects.email import Email
from app.domain.value_objects.identifiers import (
    CEDULA_PATTERN,
    URL_MAX_LENGTH,
    URL_PATTERN,
    Doi,
    Issn,
)

type AnswerValue = str | int | Decimal | date | bool | tuple[str, ...]

TEXT = "TEXT"
LONG_TEXT = "LONG_TEXT"
INTEGER = "INTEGER"
DECIMAL = "DECIMAL"
DATE = "DATE"
BOOLEAN = "BOOLEAN"
SINGLE_SELECT = "SINGLE_SELECT"
MULTI_SELECT = "MULTI_SELECT"
URL = "URL"
DOI = "DOI"
ISSN = "ISSN"
EMAIL = "EMAIL"
CEDULA = "CEDULA"
SUPPORT = "SUPPORT"

TEXT_MAX_LENGTH = 500
LONG_TEXT_MAX_LENGTH = 10_000
NUMBER_MAX_ABS = Decimal(10) ** 14  # cabe en NUMERIC(20, 6)
NUMBER_SCALE = Decimal(1).scaleb(-6)
MIN_DATE = date(1900, 1, 1)
MAX_DATE = date(2100, 12, 31)


@dataclass(frozen=True, slots=True)
class Constraints:
    """Restricciones configurables de un campo, ya resueltas para validar una respuesta."""

    min_length: int | None = None
    max_length: int | None = None
    min_value: Decimal | None = None
    max_value: Decimal | None = None
    options: frozenset[str] = frozenset()


type Parser = Callable[[object, Constraints], AnswerValue]


@dataclass(frozen=True, slots=True)
class FieldTypeSpec:
    code: str
    kind: ValueKind
    parse: Parser
    length_limit: int | None = None  # tope de longitud; None = sin min/max_length
    supports_range: bool = False  # admite min_value / max_value
    supports_options: bool = False  # requiere lista de opciones
    supports_documents: bool = False  # es un soporte: lista los tipos de documento admitidos


# ---------------- analizadores ----------------
def _text_of(raw: object) -> str:
    if not isinstance(raw, str):
        raise InvalidValue("debe ser texto")
    return raw.strip()


def _text_parser(limit: int) -> Parser:
    def parse(raw: object, c: Constraints) -> AnswerValue:
        value = _text_of(raw)
        low, high = c.min_length or 0, min(c.max_length or limit, limit)
        if not low <= len(value) <= high:
            raise InvalidValue(f"debe tener entre {low} y {high} caracteres")
        return value

    return parse


def _in_range(value: Decimal, c: Constraints) -> None:
    if abs(value) >= NUMBER_MAX_ABS:
        raise InvalidValue("está fuera del rango admitido")
    if c.min_value is not None and value < c.min_value:
        raise InvalidValue(f"debe ser mayor o igual a {c.min_value.normalize():f}")
    if c.max_value is not None and value > c.max_value:
        raise InvalidValue(f"debe ser menor o igual a {c.max_value.normalize():f}")


def _integer(raw: object, c: Constraints) -> AnswerValue:
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise InvalidValue("debe ser un número entero")
    _in_range(Decimal(raw), c)
    return raw


def _decimal(raw: object, c: Constraints) -> AnswerValue:
    if isinstance(raw, bool) or not isinstance(raw, int | float | str | Decimal):
        raise InvalidValue("debe ser un número")
    try:
        value = Decimal(str(raw).strip())
    except InvalidOperation:
        raise InvalidValue("debe ser un número") from None
    if not value.is_finite():
        raise InvalidValue("debe ser un número")
    _in_range(value, c)
    if value != value.quantize(NUMBER_SCALE):
        raise InvalidValue("admite como máximo 6 decimales")
    return value


def _date(raw: object, c: Constraints) -> AnswerValue:
    if isinstance(raw, datetime):
        raise InvalidValue("debe ser una fecha (AAAA-MM-DD)")
    if isinstance(raw, date):
        value = raw
    elif isinstance(raw, str):
        try:
            value = date.fromisoformat(raw.strip())
        except ValueError:
            raise InvalidValue("debe ser una fecha (AAAA-MM-DD)") from None
    else:
        raise InvalidValue("debe ser una fecha (AAAA-MM-DD)")
    if not MIN_DATE <= value <= MAX_DATE:
        raise InvalidValue(f"debe estar entre {MIN_DATE} y {MAX_DATE}")
    return value


def _boolean(raw: object, c: Constraints) -> AnswerValue:
    if not isinstance(raw, bool):
        raise InvalidValue("debe ser verdadero o falso")
    return raw


def _url(raw: object, c: Constraints) -> AnswerValue:
    value = _text_of(raw)
    if len(value) > URL_MAX_LENGTH or re.fullmatch(URL_PATTERN, value) is None:
        raise InvalidValue("debe ser una URL http(s) válida")
    return value


def _doi(raw: object, c: Constraints) -> AnswerValue:
    return str(Doi.parse(_text_of(raw)))


def _issn(raw: object, c: Constraints) -> AnswerValue:
    return str(Issn.parse(_text_of(raw)))


def _email(raw: object, c: Constraints) -> AnswerValue:
    return str(Email.parse(_text_of(raw)))


def _cedula(raw: object, c: Constraints) -> AnswerValue:
    """Solo dígitos (5 a 15). Tolera puntos, comas y espacios de miles: 1.003.895.357."""
    digits = _text_of(raw).replace(".", "").replace(",", "").replace(" ", "")
    if re.fullmatch(CEDULA_PATTERN, digits) is None:
        raise InvalidValue("debe contener entre 5 y 15 dígitos")
    return digits


def _single_select(raw: object, c: Constraints) -> AnswerValue:
    value = _text_of(raw)
    if value not in c.options:
        raise InvalidValue("no es una de las opciones disponibles")
    return value


def _multi_select(raw: object, c: Constraints) -> AnswerValue:
    if not isinstance(raw, list | tuple):
        raise InvalidValue("debe ser una lista de opciones")
    values = tuple(_text_of(item) for item in raw)
    if len(set(values)) != len(values):
        raise InvalidValue("no admite opciones repetidas")
    if any(v not in c.options for v in values):
        raise InvalidValue("contiene opciones que no están disponibles")
    return values


def _no_answer(raw: object, c: Constraints) -> AnswerValue:
    raise InvalidValue("es un soporte: se carga como archivo, no como respuesta")


FIELD_TYPES: Mapping[str, FieldTypeSpec] = MappingProxyType(
    {
        spec.code: spec
        for spec in (
            FieldTypeSpec(
                TEXT, ValueKind.TEXT, _text_parser(TEXT_MAX_LENGTH), length_limit=TEXT_MAX_LENGTH
            ),
            FieldTypeSpec(
                LONG_TEXT,
                ValueKind.TEXT,
                _text_parser(LONG_TEXT_MAX_LENGTH),
                length_limit=LONG_TEXT_MAX_LENGTH,
            ),
            FieldTypeSpec(INTEGER, ValueKind.NUMBER, _integer, supports_range=True),
            FieldTypeSpec(DECIMAL, ValueKind.NUMBER, _decimal, supports_range=True),
            FieldTypeSpec(DATE, ValueKind.DATE, _date),
            FieldTypeSpec(BOOLEAN, ValueKind.BOOLEAN, _boolean),
            FieldTypeSpec(SINGLE_SELECT, ValueKind.OPTION, _single_select, supports_options=True),
            FieldTypeSpec(MULTI_SELECT, ValueKind.OPTION, _multi_select, supports_options=True),
            FieldTypeSpec(URL, ValueKind.TEXT, _url),
            FieldTypeSpec(DOI, ValueKind.TEXT, _doi),
            FieldTypeSpec(ISSN, ValueKind.TEXT, _issn),
            FieldTypeSpec(EMAIL, ValueKind.TEXT, _email),
            FieldTypeSpec(CEDULA, ValueKind.TEXT, _cedula),
            FieldTypeSpec(SUPPORT, ValueKind.FILE, _no_answer, supports_documents=True),
        )
    }
)


def is_blank(raw: object) -> bool:
    """None, texto vacío o lista vacía significan "sin respuesta" (borran la respuesta previa)."""
    if raw is None:
        return True
    if isinstance(raw, str):
        return not raw.strip()
    return isinstance(raw, list | tuple) and not raw
