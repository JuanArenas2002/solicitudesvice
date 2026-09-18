from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.domain.enums.value_kind import ValueKind
from app.domain.forms import field_types as ft
from app.domain.forms.definition import FormField, FormVersion
from app.domain.forms.field_types import AnswerValue
from app.domain.forms.filled_form import FilledForm
from app.infrastructure.database.catalog import FIELD_TYPE_IDS, VALUE_KIND_IDS
from app.infrastructure.database.models.request_answer import RequestAnswerModel


def _rows_for(
    request_id: UUID, form: FormVersion, key: str, value: AnswerValue
) -> list[RequestAnswerModel]:
    """Una respuesta = una fila (multi-selección = una fila por opción elegida)."""
    field = form.field(key)
    assert field is not None and field.id is not None and form.id is not None
    base = {
        "request_id": request_id,
        "form_version_id": form.id,
        "field_id": field.id,
        "field_type_id": FIELD_TYPE_IDS[field.type_code],
        "value_kind_id": VALUE_KIND_IDS[field.spec.kind],
    }
    match field.spec.kind:
        case ValueKind.TEXT:
            return [RequestAnswerModel(**base, value_text=str(value))]
        case ValueKind.NUMBER:
            assert isinstance(value, int | Decimal)
            return [RequestAnswerModel(**base, value_number=Decimal(value))]
        case ValueKind.DATE:
            assert isinstance(value, date)
            return [RequestAnswerModel(**base, value_date=value)]
        case ValueKind.BOOLEAN:
            assert isinstance(value, bool)
            return [RequestAnswerModel(**base, value_boolean=value)]
        case ValueKind.OPTION:
            chosen = value if isinstance(value, tuple) else (str(value),)
            ids = {o.value: o.id for o in field.options}
            return [RequestAnswerModel(**base, option_id=ids[v]) for v in chosen]
    raise AssertionError(f"Clase de valor no soportada: {field.spec.kind}")  # pragma: no cover


class SqlAlchemyRequestAnswerRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def load(self, request_id: UUID, form: FormVersion) -> FilledForm:
        fields: dict[int, FormField] = {f.id: f for f in form.fields() if f.id is not None}
        rows = self._session.scalars(
            select(RequestAnswerModel)
            .where(RequestAnswerModel.request_id == request_id)
            .order_by(RequestAnswerModel.id)
        ).all()
        answers: dict[str, AnswerValue] = {}
        chosen: dict[str, list[str]] = {}
        for row in rows:
            field = fields[row.field_id]
            match field.spec.kind:
                case ValueKind.TEXT:
                    answers[field.key] = row.value_text or ""
                case ValueKind.NUMBER:
                    number = row.value_number if row.value_number is not None else Decimal(0)
                    answers[field.key] = int(number) if field.type_code == ft.INTEGER else number
                case ValueKind.DATE:
                    assert row.value_date is not None
                    answers[field.key] = row.value_date
                case ValueKind.BOOLEAN:
                    answers[field.key] = bool(row.value_boolean)
                case ValueKind.OPTION:
                    option = next(o for o in field.options if o.id == row.option_id)
                    chosen.setdefault(field.key, []).append(option.value)
        for key, values in chosen.items():
            definition = form.field(key)
            assert definition is not None
            if definition.type_code == ft.MULTI_SELECT:  # en el orden del formulario
                order = {o.value: i for i, o in enumerate(definition.options)}
                answers[key] = tuple(sorted(values, key=order.__getitem__))
            else:
                answers[key] = values[0]
        return FilledForm(request_id, form, answers)

    def replace(self, filled: FilledForm) -> None:
        # Borrar y reinsertar en dos pasos: el ORM ejecuta los INSERT antes que los DELETE y las
        # claves únicas parciales chocarían con las filas que se van a reemplazar.
        self._session.execute(
            delete(RequestAnswerModel).where(RequestAnswerModel.request_id == filled.request_id)
        )
        self._session.flush()
        for key, value in filled.answers.items():
            self._session.add_all(_rows_for(filled.request_id, filled.form, key, value))
        self._session.flush()
