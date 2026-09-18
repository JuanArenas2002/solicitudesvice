import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import NotRequired, Self, TypedDict
from uuid import UUID

from app.domain.enums.form_status import FormStatus
from app.domain.exceptions.errors import FormNotEditable, InvalidValue
from app.domain.forms.field_types import (
    CEDULA,
    FIELD_TYPES,
    AnswerValue,
    Constraints,
    FieldTypeSpec,
)
from app.domain.services.attachment_rules import ALLOWED as DOCUMENT_TYPES
from app.domain.value_objects.text import clean_optional, clean_required

KEY_PATTERN = r"^[a-z][a-z0-9_]{0,59}$"  # sin barras invertidas: igual en Python y PostgreSQL
LABEL_MAX = 200
HELP_MAX = 500
TITLE_MAX = 200
DESCRIPTION_MAX = 500
OPTION_VALUE_MAX = 100
MAX_SECTIONS = 30
MAX_FIELDS = 200
MAX_OPTIONS = 100
# Todo formulario tiene este campo, obligatorio: identifica a la persona y ordena los soportes.
IDENTITY_FIELD_KEY = "cedula"


# ---------------- entrada (lo que envía el constructor de formularios) ----------------
class OptionInput(TypedDict):
    value: str
    label: str


class FieldInput(TypedDict):
    key: str
    label: str
    type: str
    required_to_submit: NotRequired[bool]
    help_text: NotRequired[str | None]
    min_length: NotRequired[int | None]
    max_length: NotRequired[int | None]
    min_value: NotRequired[int | float | str | Decimal | None]
    max_value: NotRequired[int | float | str | Decimal | None]
    options: NotRequired[Sequence[OptionInput]]
    allowed_types: NotRequired[Sequence[str]]  # solo SUPPORT: extensiones admitidas


class SectionInput(TypedDict):
    title: str
    description: NotRequired[str | None]
    fields: Sequence[FieldInput]


# ---------------- definición ----------------
@dataclass(frozen=True, slots=True)
class FormOption:
    value: str
    label: str
    id: int | None = None


@dataclass(frozen=True, slots=True)
class FormField:
    key: str
    label: str
    type_code: str
    required_to_submit: bool = False
    help_text: str | None = None
    min_length: int | None = None
    max_length: int | None = None
    min_value: Decimal | None = None
    max_value: Decimal | None = None
    options: tuple[FormOption, ...] = ()
    allowed_types: tuple[str, ...] = ()  # solo SUPPORT: extensiones de archivo admitidas
    id: int | None = None

    @property
    def is_support(self) -> bool:
        return self.spec.supports_documents

    @property
    def spec(self) -> FieldTypeSpec:
        return FIELD_TYPES[self.type_code]

    def parse(self, raw: object) -> AnswerValue:
        """Valida y normaliza una respuesta según el tipo y las restricciones del campo."""
        constraints = Constraints(
            self.min_length,
            self.max_length,
            self.min_value,
            self.max_value,
            frozenset(o.value for o in self.options),
        )
        try:
            return self.spec.parse(raw, constraints)
        except InvalidValue as error:
            raise InvalidValue(f"{self.label}: {error.message}", field=self.key) from error


@dataclass(frozen=True, slots=True)
class FormSection:
    title: str
    fields: tuple[FormField, ...] = ()
    description: str | None = None
    id: int | None = None


def _decimal(raw: int | float | str | Decimal | None, name: str) -> Decimal | None:
    if raw is None:
        return None
    if isinstance(raw, bool):
        raise InvalidValue(f"{name} debe ser numérico", field=name)
    try:
        value = Decimal(str(raw))
    except InvalidOperation:
        raise InvalidValue(f"{name} debe ser numérico", field=name) from None
    if not value.is_finite():
        raise InvalidValue(f"{name} debe ser numérico", field=name)
    return value


def build_field(data: FieldInput) -> FormField:
    key = data.get("key")
    if not isinstance(key, str) or re.fullmatch(KEY_PATTERN, key) is None:
        raise InvalidValue(
            "key debe iniciar con minúscula y usar solo minúsculas, dígitos y _ (máx. 60)",
            field="key",
        )
    type_code = data.get("type")
    spec = FIELD_TYPES.get(type_code) if isinstance(type_code, str) else None
    if spec is None:
        raise InvalidValue(f"Tipo de campo desconocido ({type_code!r}) en '{key}'", field=key)

    min_length, max_length = data.get("min_length"), data.get("max_length")
    min_value = _decimal(data.get("min_value"), "min_value")
    max_value = _decimal(data.get("max_value"), "max_value")
    if (min_length is not None or max_length is not None) and spec.length_limit is None:
        raise InvalidValue(f"'{key}': el tipo {spec.code} no admite límites de longitud", field=key)
    if (min_value is not None or max_value is not None) and not spec.supports_range:
        raise InvalidValue(f"'{key}': el tipo {spec.code} no admite valor mínimo/máximo", field=key)
    for name, number in (("min_length", min_length), ("max_length", max_length)):
        limit = spec.length_limit or 0
        if number is not None and (
            isinstance(number, bool) or not isinstance(number, int) or not 0 <= number <= limit
        ):
            raise InvalidValue(f"'{key}': {name} debe estar entre 0 y {limit}", field=key)
    if min_length is not None and max_length is not None and min_length > max_length:
        raise InvalidValue(f"'{key}': min_length no puede superar max_length", field=key)
    if min_value is not None and max_value is not None and min_value > max_value:
        raise InvalidValue(f"'{key}': min_value no puede superar max_value", field=key)

    raw_options = data.get("options") or ()
    if raw_options and not spec.supports_options:
        raise InvalidValue(f"'{key}': el tipo {spec.code} no admite opciones", field=key)
    if len(raw_options) > MAX_OPTIONS:
        raise InvalidValue(f"'{key}': máximo {MAX_OPTIONS} opciones", field=key)
    options = tuple(
        FormOption(
            value=clean_required(o.get("value"), "option.value", OPTION_VALUE_MAX),
            label=clean_required(o.get("label"), "option.label", LABEL_MAX),
        )
        for o in raw_options
    )
    if len({o.value for o in options}) != len(options):
        raise InvalidValue(f"'{key}': hay opciones con el mismo valor", field=key)

    raw_types = data.get("allowed_types") or ()
    allowed_types = tuple(dict.fromkeys(str(t).strip().lower().lstrip(".") for t in raw_types))
    if spec.supports_documents:
        if not allowed_types:
            raise InvalidValue(f"'{key}': indique qué tipos de documento admite", field=key)
        unknown = [t for t in allowed_types if t not in DOCUMENT_TYPES]
        if unknown:
            raise InvalidValue(
                f"'{key}': tipos de documento no admitidos ({', '.join(unknown)}). "
                f"Disponibles: {', '.join(sorted(DOCUMENT_TYPES))}",
                field=key,
            )
    elif allowed_types:
        raise InvalidValue(f"'{key}': el tipo {spec.code} no admite tipos de documento", field=key)

    return FormField(
        key=key,
        label=clean_required(data.get("label"), "label", LABEL_MAX),
        type_code=spec.code,
        required_to_submit=bool(data.get("required_to_submit", False)),
        help_text=clean_optional(data.get("help_text"), "help_text", HELP_MAX),
        min_length=min_length,
        max_length=max_length,
        min_value=min_value,
        max_value=max_value,
        options=options,
        allowed_types=allowed_types,
    )


def build_section(data: SectionInput) -> FormSection:
    fields = tuple(build_field(f) for f in data.get("fields", ()))
    return FormSection(
        title=clean_required(data.get("title"), "title", TITLE_MAX),
        description=clean_optional(data.get("description"), "description", DESCRIPTION_MAX),
        fields=fields,
    )


@dataclass(eq=False)
class FormVersion:
    """Versión de un formulario de producto. Una vez publicada es inmutable.

    Las secciones y campos se identifican por posición y `key` estable; los ids los asigna la BD.
    """

    product_type_id: int
    version_number: int
    created_at: datetime
    status: FormStatus = FormStatus.BORRADOR
    created_by: UUID | None = None  # None = creada por el sistema (semilla inicial)
    published_at: datetime | None = None
    retired_at: datetime | None = None
    sections: tuple[FormSection, ...] = ()
    id: int | None = None

    @classmethod
    def new(
        cls, product_type_id: int, version_number: int, created_by: UUID | None, now: datetime
    ) -> Self:
        return cls(product_type_id, version_number, now, created_by=created_by)

    def copy_as_draft(self, version_number: int, created_by: UUID | None, now: datetime) -> Self:
        """Nuevo borrador con la misma estructura (sin ids: se generan al guardar)."""
        sections = tuple(
            replace(
                section,
                id=None,
                fields=tuple(
                    replace(f, id=None, options=tuple(replace(o, id=None) for o in f.options))
                    for f in section.fields
                ),
            )
            for section in self.sections
        )
        return type(self)(
            self.product_type_id, version_number, now, created_by=created_by, sections=sections
        )

    # ---- consulta ----
    def fields(self) -> Iterator[FormField]:
        for section in self.sections:
            yield from section.fields

    def field(self, key: str) -> FormField | None:
        return next((f for f in self.fields() if f.key == key), None)

    # ---- edición (solo borradores) ----
    def replace_structure(self, sections: Sequence[SectionInput]) -> None:
        self._ensure_draft("editar")
        if len(sections) > MAX_SECTIONS:
            raise InvalidValue(f"Máximo {MAX_SECTIONS} secciones", field="sections")
        built = tuple(build_section(s) for s in sections)
        keys = [f.key for section in built for f in section.fields]
        if len(keys) > MAX_FIELDS:
            raise InvalidValue(f"Máximo {MAX_FIELDS} campos", field="sections")
        identity = next((f for s in built for f in s.fields if f.key == IDENTITY_FIELD_KEY), None)
        if identity is not None and identity.type_code != CEDULA:
            raise InvalidValue(
                f"El campo '{IDENTITY_FIELD_KEY}' debe ser de tipo {CEDULA}",
                field=IDENTITY_FIELD_KEY,
            )
        duplicated = sorted({k for k in keys if keys.count(k) > 1})
        if duplicated:
            raise InvalidValue(f"Claves de campo repetidas: {', '.join(duplicated)}", field="key")
        self.sections = built

    def publish(self, now: datetime) -> None:
        self._ensure_draft("publicar")
        fields = tuple(self.fields())
        if not fields:
            raise InvalidValue("El formulario necesita al menos un campo", field="sections")
        identity = self.field(IDENTITY_FIELD_KEY)
        if identity is None or identity.type_code != CEDULA or not identity.required_to_submit:
            raise InvalidValue(
                f"Todo formulario debe tener el campo '{IDENTITY_FIELD_KEY}' (tipo {CEDULA}) "
                "y obligatorio para enviar",
                field=IDENTITY_FIELD_KEY,
            )
        for f in fields:
            if f.spec.supports_options and not f.options:
                raise InvalidValue(f"El campo '{f.key}' necesita al menos una opción", field=f.key)
        self.status = FormStatus.PUBLICADA
        self.published_at = now

    def retire(self, now: datetime) -> None:
        if self.status is not FormStatus.PUBLICADA:
            raise FormNotEditable("Solo una versión publicada puede retirarse")
        self.status = FormStatus.RETIRADA
        self.retired_at = now

    def _ensure_draft(self, action: str) -> None:
        if self.status is not FormStatus.BORRADOR:
            raise FormNotEditable(f"Solo un borrador puede {action}: la versión está {self.status}")
