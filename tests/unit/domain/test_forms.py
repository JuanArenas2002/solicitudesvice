from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from app.domain.entities.product_type import ProductType
from app.domain.enums.form_status import FormStatus
from app.domain.exceptions.errors import FormNotEditable, InvalidValue
from app.domain.forms.definition import (
    MAX_FIELDS,
    MAX_SECTIONS,
    FieldInput,
    FormVersion,
    SectionInput,
    build_field,
)
from app.domain.forms.field_types import FIELD_TYPES, is_blank
from app.domain.forms.filled_form import FilledForm
from tests.unit.domain.factories import FORM, NOW, SAMPLE_SECTIONS

OPTIONS = [{"value": "a", "label": "Opción A"}, {"value": "b", "label": "Opción B"}]
CEDULA: FieldInput = {
    "key": "cedula",
    "label": "Cédula",
    "type": "CEDULA",
    "required_to_submit": True,
}


def field(type_code: str, **extra: object) -> FieldInput:
    return {"key": "campo", "label": "Campo", "type": type_code, **extra}  # type: ignore[typeddict-item]


def parse(type_code: str, raw: object, **extra: object) -> object:
    return build_field(field(type_code, **extra)).parse(raw)


# ---------------- tipos de campo: validación y normalización ----------------
@pytest.mark.parametrize(
    ("type_code", "raw", "expected"),
    [
        ("TEXT", "  hola  ", "hola"),
        ("LONG_TEXT", "x" * 5000, "x" * 5000),
        ("INTEGER", 2025, 2025),
        ("DECIMAL", "12.5", Decimal("12.5")),
        ("DECIMAL", 3, Decimal("3")),
        ("DECIMAL", 0.25, Decimal("0.25")),
        ("DATE", "2024-05-01", date(2024, 5, 1)),
        ("DATE", date(2024, 5, 1), date(2024, 5, 1)),
        ("BOOLEAN", True, True),
        ("BOOLEAN", False, False),
        ("URL", " https://example.org/a?b=1 ", "https://example.org/a?b=1"),
        ("DOI", " 10.1234/abc.1 ", "10.1234/abc.1"),
        ("ISSN", "0378-595x", "0378-595X"),
        ("ISSN", "03785958", "0378-5958"),
        ("ISSN", " 0378 595x ", "0378-595X"),
        ("EMAIL", " Ana@Example.ORG ", "ana@example.org"),
        ("CEDULA", " 1.003.895.357 ", "1003895357"),
        ("CEDULA", "12345", "12345"),
        ("CEDULA", "1,003 895 357", "1003895357"),
    ],
)
def test_valid_answers_are_normalized(type_code: str, raw: object, expected: object) -> None:
    assert parse(type_code, raw) == expected


@pytest.mark.parametrize(
    ("type_code", "raw"),
    [
        ("TEXT", 123),
        ("TEXT", "x" * 501),
        ("LONG_TEXT", "x" * 10_001),
        ("INTEGER", "2025"),
        ("INTEGER", 2025.5),
        ("INTEGER", True),
        ("INTEGER", 10**14),
        ("DECIMAL", "abc"),
        ("DECIMAL", "NaN"),
        ("DECIMAL", "Infinity"),
        ("DECIMAL", "1.1234567"),  # más de 6 decimales
        ("DECIMAL", True),
        ("DATE", "01/05/2024"),
        ("DATE", "2024-13-40"),
        ("DATE", "1800-01-01"),
        ("DATE", 20240501),
        ("BOOLEAN", "true"),
        ("BOOLEAN", 1),
        ("URL", "ftp://example.org"),
        ("URL", "https://ex ample.org"),
        ("URL", "https://" + "a" * 2050),
        ("DOI", "no-es-doi"),
        ("ISSN", "1234-56"),
        ("EMAIL", "sin-arroba"),
        ("CEDULA", "1234"),
        ("CEDULA", "1" * 16),
        ("CEDULA", "10-038"),
        ("CEDULA", "abc12345"),
        ("CEDULA", 1003895357),
    ],
)
def test_invalid_answers_are_rejected_with_the_field_key(type_code: str, raw: object) -> None:
    with pytest.raises(InvalidValue) as error:
        parse(type_code, raw)
    assert error.value.field == "campo" and error.value.message.startswith("Campo:")


def test_length_and_range_constraints_apply() -> None:
    assert parse("TEXT", "abc", min_length=3, max_length=5) == "abc"
    for bad in ("ab", "abcdef"):
        with pytest.raises(InvalidValue):
            parse("TEXT", bad, min_length=3, max_length=5)
    assert parse("INTEGER", 5, min_value=1, max_value=5) == 5
    for out_of_range in (0, 6):
        with pytest.raises(InvalidValue):
            parse("INTEGER", out_of_range, min_value=1, max_value=5)
    with pytest.raises(InvalidValue):
        parse("DECIMAL", "0.5", min_value="1.5")


def test_selects_only_accept_declared_options() -> None:
    assert parse("SINGLE_SELECT", "a", options=OPTIONS) == "a"
    assert parse("MULTI_SELECT", ["a", "b"], options=OPTIONS) == ("a", "b")
    for bad in ("z", 1, ["a"]):
        with pytest.raises(InvalidValue):
            parse("SINGLE_SELECT", bad, options=OPTIONS)
    for bad in (["a", "a"], ["a", "z"], "a", 5):
        with pytest.raises(InvalidValue):
            parse("MULTI_SELECT", bad, options=OPTIONS)


def test_blank_values_mean_no_answer() -> None:
    blanks: tuple[object, ...] = (None, "", "   ", [], ())
    filled: tuple[object, ...] = (0, False, "x", ["a"])
    assert all(is_blank(v) for v in blanks)
    assert not any(is_blank(v) for v in filled)


def test_every_registered_type_is_covered_by_these_tests() -> None:
    covered = {
        "TEXT", "LONG_TEXT", "INTEGER", "DECIMAL", "DATE", "BOOLEAN",
        "SINGLE_SELECT", "MULTI_SELECT", "URL", "DOI", "ISSN", "EMAIL", "CEDULA", "SUPPORT",
    }  # fmt: skip
    assert set(FIELD_TYPES) == covered  # un tipo nuevo obliga a agregar sus casos aquí


# ---------------- definición de campos ----------------
@pytest.mark.parametrize(
    "data",
    [
        field("NO_EXISTE"),
        {**field("TEXT"), "key": "Mayus"},
        {**field("TEXT"), "key": "1abc"},
        {**field("TEXT"), "key": "con espacio"},
        {**field("TEXT"), "key": "x" * 61},
        {**field("TEXT"), "label": "  "},
        field("DATE", max_length=10),  # longitud solo en tipos de texto
        field("TEXT", min_value=1),  # rango solo en tipos numéricos
        field("TEXT", min_length=5, max_length=2),
        field("TEXT", max_length=501),
        field("TEXT", min_length=-1),
        field("INTEGER", min_value=10, max_value=1),
        field("INTEGER", min_value="abc"),
        field("TEXT", options=OPTIONS),  # opciones solo en selecciones
        field(
            "SINGLE_SELECT", options=[{"value": "a", "label": "A"}, {"value": "a", "label": "B"}]
        ),
        field("SINGLE_SELECT", options=[{"value": " ", "label": "A"}]),
    ],
)
def test_invalid_field_definitions_are_rejected(data: FieldInput) -> None:
    with pytest.raises(InvalidValue):
        build_field(data)


def test_field_definition_is_normalized() -> None:
    built = build_field(
        field("SINGLE_SELECT", label="  Tipo  ", help_text="  ayuda ", options=OPTIONS)
    )
    assert built.label == "Tipo" and built.help_text == "ayuda"
    assert [o.value for o in built.options] == ["a", "b"] and not built.required_to_submit


# ---------------- versiones de formulario ----------------
def draft(sections: list[SectionInput] | None = None) -> FormVersion:
    version = FormVersion.new(product_type_id=1, version_number=1, created_by=uuid4(), now=NOW)
    if sections is not None:
        version.replace_structure(sections)
    return version


def test_replace_structure_builds_sections_in_order() -> None:
    version = draft(SAMPLE_SECTIONS)
    assert [s.title for s in version.sections] == ["Datos del artículo", "Revista"]
    assert [f.key for f in version.fields()] == [
        "cedula",
        "titulo",
        "anio",
        "doi",
        "revista",
        "issn",
    ]
    assert version.field("anio") is not None and version.field("nada") is None


def test_replace_structure_rejects_duplicated_keys_and_limits() -> None:
    dup: list[SectionInput] = [
        {"title": "A", "fields": [field("TEXT")]},
        {"title": "B", "fields": [field("TEXT")]},  # misma key "campo"
    ]
    with pytest.raises(InvalidValue, match="repetidas"):
        draft().replace_structure(dup)
    with pytest.raises(InvalidValue):
        draft().replace_structure([{"title": "  ", "fields": []}])
    with pytest.raises(InvalidValue):
        draft().replace_structure(
            [{"title": f"S{i}", "fields": []} for i in range(MAX_SECTIONS + 1)]
        )
    many = [{**field("TEXT"), "key": f"c{i}"} for i in range(MAX_FIELDS + 1)]
    with pytest.raises(InvalidValue):
        draft().replace_structure([{"title": "A", "fields": many}])  # type: ignore[typeddict-item]


def test_a_failed_replacement_keeps_the_previous_structure() -> None:
    version = draft(SAMPLE_SECTIONS)
    with pytest.raises(InvalidValue):
        version.replace_structure([{"title": "X", "fields": [field("NO_EXISTE")]}])
    assert len(version.sections) == 2


def test_publish_lifecycle_and_immutability() -> None:
    version = draft(SAMPLE_SECTIONS)
    version.publish(NOW)
    assert version.status is FormStatus.PUBLICADA and version.published_at == NOW
    with pytest.raises(FormNotEditable):
        version.replace_structure([])  # una publicada es inmutable
    with pytest.raises(FormNotEditable):
        version.publish(NOW)
    version.retire(NOW)
    assert version.retired_at == NOW and version.status is FormStatus.RETIRADA  # type: ignore[comparison-overlap]
    with pytest.raises(FormNotEditable):
        version.retire(NOW)
    with pytest.raises(FormNotEditable):
        version.replace_structure([])


def test_cannot_publish_an_empty_form_or_selects_without_options() -> None:
    with pytest.raises(InvalidValue):
        draft().publish(NOW)
    with pytest.raises(InvalidValue):
        draft([{"title": "A", "fields": []}]).publish(NOW)
    with pytest.raises(InvalidValue, match="opción"):
        draft([{"title": "A", "fields": [CEDULA, field("SINGLE_SELECT")]}]).publish(NOW)
    assert draft().status is FormStatus.BORRADOR


def test_only_published_versions_can_be_retired() -> None:
    with pytest.raises(FormNotEditable):
        draft(SAMPLE_SECTIONS).retire(NOW)


def test_copy_as_draft_keeps_structure_without_ids_and_is_independent() -> None:
    source = FormVersion.new(1, 1, None, NOW)
    source.replace_structure(
        [
            {
                "title": "S",
                "fields": [
                    CEDULA,
                    field("SINGLE_SELECT", options=OPTIONS, required_to_submit=True),
                ],
            }
        ]
    )
    source.publish(NOW)
    source.id = 7
    copy = source.copy_as_draft(2, uuid4(), NOW)
    assert copy.status is FormStatus.BORRADOR and copy.version_number == 2 and copy.id is None
    assert [f.key for f in copy.fields()] == ["cedula", "campo"]
    campo = copy.field("campo")
    assert campo is not None and campo.required_to_submit
    assert all(o.id is None for o in campo.options)
    copy.replace_structure([])  # editar la copia no toca la original
    assert len(source.sections) == 1


# ---------------- respuestas de una solicitud ----------------
def test_filled_form_requires_a_non_draft_form() -> None:
    with pytest.raises(InvalidValue):
        FilledForm.empty(uuid4(), draft(SAMPLE_SECTIONS))


def test_apply_validates_normalizes_and_can_clear() -> None:
    filled = FilledForm.empty(uuid4(), FORM).apply(
        {"titulo": "  Un título  ", "anio": 2024, "doi": "10.1234/x"}
    )
    assert dict(filled.answers) == {"titulo": "Un título", "anio": 2024, "doi": "10.1234/x"}
    cleared = filled.apply({"doi": None, "titulo": "   "})  # vacío = borrar la respuesta
    assert dict(cleared.answers) == {"anio": 2024}
    assert filled.answers["titulo"] == "Un título"  # inmutable: la anterior no cambia


@pytest.mark.parametrize(
    "changes",
    [{"no_existe": "x"}, {"anio": 1800}, {"anio": "2024"}, {"doi": "mal"}, {"issn": "1234"}],
)
def test_apply_rejects_invalid_answers_and_unknown_fields(changes: dict[str, object]) -> None:
    with pytest.raises(InvalidValue):
        FilledForm.empty(uuid4(), FORM).apply(changes)


def test_apply_is_all_or_nothing() -> None:
    filled = FilledForm.empty(uuid4(), FORM).apply({"titulo": "T"})
    with pytest.raises(InvalidValue):
        filled.apply({"anio": 2024, "doi": "mal"})
    assert dict(filled.answers) == {"titulo": "T"}


def test_missing_for_submission_follows_form_order() -> None:
    filled = FilledForm.empty(uuid4(), FORM)
    assert filled.missing_for_submission() == ("cedula", "titulo", "anio", "revista")
    partial = filled.apply({"revista": "R", "titulo": "T", "cedula": "1003895357"})
    assert partial.missing_for_submission() == ("anio",)
    complete = filled.apply({"revista": "R", "titulo": "T", "anio": 2024, "cedula": "12345"})
    assert complete.missing_for_submission() == ()


def test_changed_keys_reports_added_removed_and_modified() -> None:
    before = FilledForm.empty(uuid4(), FORM).apply({"titulo": "A", "anio": 2020})
    after = before.apply({"titulo": "B", "doi": "10.1234/x", "anio": None})
    assert before.changed_keys(after) == ("anio", "doi", "titulo")


def test_answers_are_read_only() -> None:
    filled = FilledForm.empty(uuid4(), FORM).apply({"titulo": "A"})
    with pytest.raises(TypeError):
        filled.answers["titulo"] = "B"  # type: ignore[index]


# ---------------- tipo de producto ----------------
def test_product_type_is_normalized_and_validated() -> None:
    pt = ProductType.create(" libro_capitulo ", "  Capítulo de libro ", "  desc  ", NOW)
    assert (pt.code, pt.name, pt.description, pt.is_active) == (
        "LIBRO_CAPITULO",
        "Capítulo de libro",
        "desc",
        True,
    )
    for bad in ("", "1ABC", "A", "CON ESPACIO", "x" * 31, "TILDE_Ñ"):
        with pytest.raises(InvalidValue):
            ProductType.create(bad, "Nombre", None, NOW)
    with pytest.raises(InvalidValue):
        ProductType.create("LIBRO", "  ", None, NOW)


def test_product_type_update_and_deactivation() -> None:
    pt = ProductType.create("LIBRO", "Libro", None, NOW)
    later = NOW.replace(hour=15)
    pt.update(later, name="Libro de investigación", is_active=False)
    assert (pt.name, pt.is_active, pt.updated_at, pt.code) == (
        "Libro de investigación",
        False,
        later,
        "LIBRO",
    )
    pt.update(later, description="Nueva")
    assert pt.description == "Nueva" and pt.name == "Libro de investigación"


# ---------------- la cédula es obligatoria en todo formulario ----------------
def test_every_form_needs_a_required_cedula_field_to_be_published() -> None:
    other: FieldInput = {"key": "titulo", "label": "Título", "type": "TEXT"}
    cases: list[list[FieldInput]] = [
        [other],  # sin cédula
        [{**CEDULA, "required_to_submit": False}, other],  # cédula opcional
    ]
    for fields in cases:
        with pytest.raises(InvalidValue) as error:
            draft([{"title": "A", "fields": fields}]).publish(NOW)
        assert error.value.field == "cedula"
    draft([{"title": "A", "fields": [other, CEDULA]}]).publish(NOW)  # en cualquier posición


def test_the_reserved_cedula_key_must_be_of_type_cedula() -> None:
    with pytest.raises(InvalidValue) as error:
        draft().replace_structure(
            [{"title": "A", "fields": [{"key": "cedula", "label": "Doc", "type": "TEXT"}]}]
        )
    assert error.value.field == "cedula"


def test_filled_form_exposes_the_normalized_cedula() -> None:
    filled = FilledForm.empty(uuid4(), FORM)
    assert filled.cedula is None
    assert filled.apply({"cedula": "1.003.895.357"}).cedula == "1003895357"
