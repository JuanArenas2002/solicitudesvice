from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

import pytest

from app.domain.exceptions.errors import InvalidValue
from app.domain.forms.definition import FieldInput, FormVersion, SectionInput
from app.domain.forms.filled_form import FilledForm

NOW = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)
CEDULA: FieldInput = {
    "key": "cedula",
    "label": "Cédula",
    "type": "CEDULA",
    "required_to_submit": True,
}


def support(**extra: object) -> FieldInput:
    base: dict[str, object] = {
        "key": "acta",
        "label": "Acta",
        "type": "SUPPORT",
        "allowed_types": ["pdf"],
    }
    return cast(FieldInput, {**base, **extra})


def form(*fields: FieldInput) -> FormVersion:
    version = FormVersion.new(1, 1, None, NOW)
    sections: list[SectionInput] = [{"title": "S", "fields": [CEDULA, *fields]}]
    version.replace_structure(sections)
    version.publish(NOW)
    return version


def test_a_support_field_lists_the_document_types_it_accepts() -> None:
    field = form(support(allowed_types=[" PDF ", ".docx", "pdf"])).field("acta")
    assert field is not None and field.is_support
    assert field.allowed_types == ("pdf", "docx")  # normalizados y sin repetir


@pytest.mark.parametrize(
    "extra",
    [
        {"allowed_types": []},  # un soporte debe decir qué documentos recibe
        {"allowed_types": ["exe"]},
        {"allowed_types": ["pdf", "html"]},
    ],
)
def test_a_support_field_needs_valid_document_types(extra: dict[str, object]) -> None:
    with pytest.raises(InvalidValue) as error:
        form(support(**extra))
    assert error.value.field == "acta"


def test_only_support_fields_take_document_types() -> None:
    with pytest.raises(InvalidValue):
        form({"key": "titulo", "label": "T", "type": "TEXT", "allowed_types": ["pdf"]})


def test_a_support_is_never_answered_with_a_value() -> None:
    filled = FilledForm.empty(uuid4(), form(support()))
    with pytest.raises(InvalidValue):
        filled.apply({"acta": "algo"})
    assert filled.apply({"acta": None}).answers == {}  # vaciar no hace nada


def test_a_required_support_is_satisfied_by_an_attachment_not_an_answer() -> None:
    filled = FilledForm.empty(uuid4(), form(support(required_to_submit=True))).apply(
        {"cedula": "1003895357"}
    )
    assert filled.missing_for_submission() == ("acta",)
    assert filled.with_attachments(frozenset({"acta"})).missing_for_submission() == ()
    # aplicar respuestas después no pierde qué soportes ya tienen archivo
    assert filled.with_attachments(frozenset({"acta"})).apply({}).attached_keys == {"acta"}


def test_an_optional_support_never_blocks_the_submission() -> None:
    filled = FilledForm.empty(uuid4(), form(support())).apply({"cedula": "1003895357"})
    assert filled.missing_for_submission() == ()


def test_a_new_draft_copies_the_document_types() -> None:
    copy = form(support(allowed_types=["pdf", "zip"])).copy_as_draft(2, None, NOW)
    field = copy.field("acta")
    assert field is not None and field.allowed_types == ("pdf", "zip")
