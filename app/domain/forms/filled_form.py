from collections.abc import Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType
from uuid import UUID

from app.domain.enums.form_status import FormStatus
from app.domain.exceptions.errors import InvalidValue
from app.domain.forms.definition import IDENTITY_FIELD_KEY, FormVersion
from app.domain.forms.field_types import AnswerValue, is_blank


@dataclass(frozen=True, slots=True)
class FilledForm:
    """Respuestas de una solicitud, siempre validadas contra la versión de formulario que usa.

    Cumple el contrato ProductDetail que consume el agregado de solicitudes (`submit`/`resubmit`).
    """

    request_id: UUID
    form: FormVersion
    answers: Mapping[str, AnswerValue]
    attached_keys: frozenset[str] = frozenset()  # soportes (campos SUPPORT) con algún archivo

    def __post_init__(self) -> None:
        if self.form.status is FormStatus.BORRADOR:
            raise InvalidValue(
                "Una solicitud no puede usar un formulario en borrador", field="form"
            )
        object.__setattr__(self, "answers", MappingProxyType(dict(self.answers)))

    @classmethod
    def empty(cls, request_id: UUID, form: FormVersion) -> "FilledForm":
        return cls(request_id, form, {})

    def with_attachments(self, keys: frozenset[str]) -> "FilledForm":
        return replace(self, attached_keys=keys)

    def apply(self, changes: Mapping[str, object]) -> "FilledForm":
        """Aplica cambios parciales: una respuesta vacía/None borra la anterior."""
        updated = dict(self.answers)
        for key, raw in changes.items():
            field = self.form.field(key)
            if field is None:
                raise InvalidValue(f"El formulario no tiene el campo '{key}'", field=key)
            if is_blank(raw):
                updated.pop(key, None)
            else:
                updated[key] = field.parse(raw)
        return FilledForm(self.request_id, self.form, updated, self.attached_keys)

    def changed_keys(self, other: "FilledForm") -> tuple[str, ...]:
        keys = set(self.answers) | set(other.answers)
        return tuple(k for k in sorted(keys) if self.answers.get(k) != other.answers.get(k))

    @property
    def cedula(self) -> str | None:
        """Cédula diligenciada (define la carpeta de los soportes)."""
        value = self.answers.get(IDENTITY_FIELD_KEY)
        return value if isinstance(value, str) else None

    def missing_for_submission(self) -> tuple[str, ...]:
        """Claves de los campos obligatorios sin respuesta, en el orden del formulario."""
        answered = self.answers.keys() | self.attached_keys
        return tuple(
            f.key for f in self.form.fields() if f.required_to_submit and f.key not in answered
        )
