import pytest

from app.application.commands.forms import (
    CreateProductTypeCommand,
    ReplaceFormDraftCommand,
    UpdateProductTypeCommand,
)
from app.application.dto.page import PageRequest
from app.domain.enums.audit_action import AuditAction
from app.domain.enums.form_status import FormStatus
from app.domain.enums.role import Role
from app.domain.exceptions.errors import (
    DuplicateProductType,
    Forbidden,
    FormDraftExists,
    FormNotEditable,
    FormVersionNotFound,
    InvalidValue,
    ProductTypeNotFound,
)
from app.domain.forms.definition import SectionInput
from app.domain.forms.filled_form import FilledForm
from app.domain.value_objects.actor import Actor
from tests.unit.application.conftest import CTX, World

BOOK: list[SectionInput] = [
    {
        "title": "Datos del libro",
        "fields": [
            {"key": "cedula", "label": "Cédula", "type": "CEDULA", "required_to_submit": True},
            {"key": "titulo", "label": "Título", "type": "TEXT", "required_to_submit": True},
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
        ],
    }
]


@pytest.fixture(params=[Role.ADMIN, Role.ADMINISTRATIVO])
def manager(request: pytest.FixtureRequest, world: World) -> Actor:
    """Tanto el ADMIN como el ADMINISTRATIVO pueden gestionar formularios."""
    return world.actor_for(world.add_user(request.param))


def new_type(world: World, manager: Actor, code: str = "LIBRO"):
    return world.create_product_type().execute(
        manager, CreateProductTypeCommand(code, "Libro", "Libro de investigación"), CTX
    )


def published_book(world: World, manager: Actor):
    product_type, draft = new_type(world, manager)
    assert draft.id is not None and product_type.id is not None
    world.replace_draft().execute(manager, ReplaceFormDraftCommand(draft.id, BOOK), CTX)
    return product_type, world.publish().execute(manager, draft.id, CTX)


# ---------------- permisos ----------------
@pytest.mark.parametrize("role", [Role.MENTOR])
def test_mentors_cannot_manage_forms(world: World, role: Role) -> None:
    actor = world.actor_for(world.add_user(role))
    with pytest.raises(Forbidden):
        world.create_product_type().execute(actor, CreateProductTypeCommand("LIBRO", "Libro"), CTX)
    for call in (
        lambda: world.update_product_type().execute(
            actor, UpdateProductTypeCommand(1, name="X"), CTX
        ),
        lambda: world.create_draft().execute(actor, 1, CTX),
        lambda: world.replace_draft().execute(actor, ReplaceFormDraftCommand(1, BOOK), CTX),
        lambda: world.publish().execute(actor, 1, CTX),
        lambda: world.get_form().execute(actor, 1),
        lambda: world.list_versions().execute(actor, 1),
        lambda: world.seed_forms().execute(actor, CTX),
    ):
        with pytest.raises(Forbidden):
            call()
    assert world.db.state.product_types == {} and world.db.state.forms == {}


# ---------------- crear un producto nuevo ----------------
def test_creating_a_product_type_opens_its_first_draft(world: World, manager: Actor) -> None:
    product_type, draft = new_type(world, manager, " libro ")

    assert product_type.code == "LIBRO" and product_type.is_active and product_type.id is not None
    assert draft.status is FormStatus.BORRADOR and draft.version_number == 1
    assert draft.product_type_id == product_type.id and draft.created_by == manager.user_id
    assert world.audit_actions() == [
        AuditAction.PRODUCT_TYPE_CREATED,
        AuditAction.FORM_DRAFT_CREATED,
    ]
    assert all(e.actor_id == manager.user_id for e in world.db.state.audit)


def test_duplicate_or_invalid_product_code_leaves_no_trace(world: World, manager: Actor) -> None:
    new_type(world, manager)
    before = (
        len(world.db.state.product_types),
        len(world.db.state.forms),
        len(world.db.state.audit),
    )
    with pytest.raises(DuplicateProductType):
        new_type(world, manager)
    with pytest.raises(InvalidValue):
        new_type(world, manager, "1 mal código")
    after = (
        len(world.db.state.product_types),
        len(world.db.state.forms),
        len(world.db.state.audit),
    )
    assert after == before


def test_update_product_type_audits_field_names(world: World, manager: Actor) -> None:
    product_type, _ = new_type(world, manager)
    assert product_type.id is not None
    updated = world.update_product_type().execute(
        manager, UpdateProductTypeCommand(product_type.id, name="Libros", is_active=False), CTX
    )
    assert (updated.name, updated.is_active) == ("Libros", False)
    (entry,) = world.audit_of(AuditAction.PRODUCT_TYPE_UPDATED)
    assert entry.detail == {"product_type_id": product_type.id, "changed": ["name", "is_active"]}
    with pytest.raises(ProductTypeNotFound):
        world.update_product_type().execute(manager, UpdateProductTypeCommand(999, name="X"), CTX)


# ---------------- editar y publicar ----------------
def test_replace_draft_saves_the_whole_document(world: World, manager: Actor) -> None:
    _, draft = new_type(world, manager)
    assert draft.id is not None

    saved = world.replace_draft().execute(manager, ReplaceFormDraftCommand(draft.id, BOOK), CTX)

    assert [f.key for f in saved.fields()] == ["cedula", "titulo", "idioma", "isbn"]
    assert all(f.id is not None for f in saved.fields())
    (entry,) = world.audit_of(AuditAction.FORM_DRAFT_SAVED)
    assert entry.detail == {"form_version_id": draft.id, "sections": 1, "fields": 4}
    # guardar de nuevo reemplaza, no acumula
    again = world.replace_draft().execute(manager, ReplaceFormDraftCommand(draft.id, BOOK[:1]), CTX)
    assert len(list(again.fields())) == 4


def test_invalid_definition_is_rejected_and_the_draft_is_untouched(
    world: World, manager: Actor
) -> None:
    _, draft = new_type(world, manager)
    assert draft.id is not None
    world.replace_draft().execute(manager, ReplaceFormDraftCommand(draft.id, BOOK), CTX)
    bad: list[SectionInput] = [
        {"title": "X", "fields": [{"key": "a", "label": "A", "type": "NADA"}]}
    ]
    with pytest.raises(InvalidValue):
        world.replace_draft().execute(manager, ReplaceFormDraftCommand(draft.id, bad), CTX)
    stored = world.get_form().execute(manager, draft.id)
    assert [f.key for f in stored.fields()] == ["cedula", "titulo", "idioma", "isbn"]


def test_publishing_makes_the_form_immutable(world: World, manager: Actor) -> None:
    _, version = published_book(world, manager)
    assert version.id is not None and version.status is FormStatus.PUBLICADA
    with pytest.raises(FormNotEditable):
        world.replace_draft().execute(manager, ReplaceFormDraftCommand(version.id, BOOK), CTX)
    with pytest.raises(FormNotEditable):
        world.publish().execute(manager, version.id, CTX)  # ya publicada
    with pytest.raises(FormVersionNotFound):
        world.replace_draft().execute(manager, ReplaceFormDraftCommand(999, BOOK), CTX)


def test_empty_form_cannot_be_published(world: World, manager: Actor) -> None:
    _, draft = new_type(world, manager)
    assert draft.id is not None
    with pytest.raises(InvalidValue):
        world.publish().execute(manager, draft.id, CTX)
    assert world.get_form().execute(manager, draft.id).status is FormStatus.BORRADOR
    assert world.audit_of(AuditAction.FORM_PUBLISHED) == []


def test_new_version_replaces_the_published_one_atomically(world: World, manager: Actor) -> None:
    product_type, v1 = published_book(world, manager)
    assert product_type.id is not None and v1.id is not None

    v2_draft = world.create_draft().execute(manager, product_type.id, CTX)
    assert v2_draft.version_number == 2 and v2_draft.status is FormStatus.BORRADOR
    assert [f.key for f in v2_draft.fields()] == [
        "cedula",
        "titulo",
        "idioma",
        "isbn",
    ]  # copia de la v1
    assert v2_draft.id != v1.id and all(
        f.id != o.id for f, o in zip(v2_draft.fields(), v1.fields(), strict=True)
    )

    changed: list[SectionInput] = [
        {
            **BOOK[0],
            "fields": [
                *BOOK[0]["fields"],
                {"key": "editorial", "label": "Editorial", "type": "TEXT"},
            ],
        }
    ]
    assert v2_draft.id is not None
    world.replace_draft().execute(manager, ReplaceFormDraftCommand(v2_draft.id, changed), CTX)
    v2 = world.publish().execute(manager, v2_draft.id, CTX)

    versions = world.list_versions().execute(manager, product_type.id)
    assert [(v.version_number, v.status) for v in versions] == [
        (2, FormStatus.PUBLICADA),
        (1, FormStatus.RETIRADA),
    ]
    assert versions[1].retired_at == world.clock.now()
    assert "editorial" in [f.key for f in v2.fields()]
    # la v1 conserva su estructura original para las solicitudes que ya la usan
    assert "editorial" not in [f.key for f in world.get_form().execute(manager, v1.id).fields()]
    (entry,) = [
        e for e in world.audit_of(AuditAction.FORM_PUBLISHED) if e.detail["version_number"] == 2
    ]
    assert entry.detail["replaced_version_number"] == 1


def test_only_one_draft_at_a_time(world: World, manager: Actor) -> None:
    product_type, draft = new_type(world, manager)
    assert product_type.id is not None
    with pytest.raises(FormDraftExists):
        world.create_draft().execute(manager, product_type.id, CTX)
    with pytest.raises(ProductTypeNotFound):
        world.create_draft().execute(manager, 999, CTX)


# ---------------- lo que ve el mentor ----------------
def test_mentor_sees_only_the_published_form_of_active_products(
    world: World, manager: Actor
) -> None:
    mentor = world.actor_for(world.add_user(Role.MENTOR))
    product_type, draft = new_type(world, manager)
    assert product_type.id is not None and draft.id is not None

    with pytest.raises(FormVersionNotFound):  # aún solo hay borrador
        world.published_form().execute(mentor, product_type.id)

    world.replace_draft().execute(manager, ReplaceFormDraftCommand(draft.id, BOOK), CTX)
    world.publish().execute(manager, draft.id, CTX)
    form = world.published_form().execute(mentor, product_type.id)
    assert form.status is FormStatus.PUBLICADA and [s.title for s in form.sections] == [
        "Datos del libro"
    ]

    world.update_product_type().execute(
        manager, UpdateProductTypeCommand(product_type.id, is_active=False), CTX
    )
    with pytest.raises(ProductTypeNotFound):  # desactivado: el mentor ya no puede iniciarlo
        world.published_form().execute(mentor, product_type.id)
    with pytest.raises(ProductTypeNotFound):
        world.published_form().execute(mentor, 999)


def test_product_type_listing_depends_on_the_role(world: World, manager: Actor) -> None:
    mentor = world.actor_for(world.add_user(Role.MENTOR))
    new_type(world, manager, "LIBRO")
    _, _ = new_type(world, manager, "PATENTE")
    patente = world.db.state.product_types
    inactive = next(p for p in patente.values() if p.code == "PATENTE")
    assert inactive.id is not None
    world.update_product_type().execute(
        manager, UpdateProductTypeCommand(inactive.id, is_active=False), CTX
    )

    assert {p.code for p in world.list_product_types().execute(manager, PageRequest()).items} == {
        "LIBRO",
        "PATENTE",
    }
    assert {p.code for p in world.list_product_types().execute(mentor, PageRequest()).items} == {
        "LIBRO"
    }


# ---------------- historia completa: un producto nuevo sin tocar la base ----------------
def test_a_new_product_becomes_requestable_through_the_system_alone(
    world: World, manager: Actor
) -> None:
    mentor = world.actor_for(world.add_user(Role.MENTOR))
    _, form = published_book(world, manager)

    # lo que hará el módulo de solicitudes: llenar y validar respuestas contra la versión publicada
    filled = FilledForm.empty(__import__("uuid").uuid4(), form).apply(
        {"cedula": "1003895357", "titulo": "Metodologías de investigación", "idioma": "es"}
    )
    assert filled.missing_for_submission() == ()
    with pytest.raises(InvalidValue):
        filled.apply({"idioma": "fr"})  # opción inexistente
    assert mentor.role is Role.MENTOR


# ---------------- formulario inicial de artículos ----------------
def test_seed_loads_the_article_form_once(world: World) -> None:
    admin = world.actor_for(world.add_user(Role.ADMIN))

    assert world.seed_forms().execute(admin, CTX) is True
    assert world.seed_forms().execute(admin, CTX) is False  # idempotente

    (product_type,) = world.db.state.product_types.values()
    assert (product_type.code, product_type.name) == ("ARTICULO", "Artículo científico")
    assert product_type.id is not None
    form = world.published_form().execute(
        world.actor_for(world.add_user(Role.MENTOR)), product_type.id
    )
    assert [s.title for s in form.sections] == [
        "Datos del artículo",
        "Datos de la revista",
        "Soportes",
    ]
    assert [f.key for f in form.fields()] == [
        "cedula", "titulo", "anio_publicacion", "fecha_publicacion", "doi", "url",
        "revista", "issn", "eissn", "volumen", "numero", "paginas",
        "soporte_articulo", "soporte_aceptacion",
    ]  # fmt: skip
    required = {f.key for f in form.fields() if f.required_to_submit}
    assert required == {"cedula", "titulo", "anio_publicacion", "revista", "soporte_articulo"}
    assert len(world.db.state.forms) == 1 and len(world.audit_of(AuditAction.FORM_PUBLISHED)) == 1


def test_seed_completes_a_half_created_product(world: World, manager: Actor) -> None:
    """Si ya existía el producto ARTICULO con solo un borrador vacío, la carga lo completa."""
    world.create_product_type().execute(
        manager, CreateProductTypeCommand("ARTICULO", "Artículo científico"), CTX
    )
    assert world.seed_forms().execute(manager, CTX) is True
    (product_type,) = world.db.state.product_types.values()
    assert product_type.id is not None
    assert len(list(world.get_form().execute(manager, min(world.db.state.forms)).fields())) == 14


def test_article_form_accepts_a_realistic_answer_set(world: World) -> None:
    admin = world.actor_for(world.add_user(Role.ADMIN))
    world.seed_forms().execute(admin, CTX)
    form = next(iter(world.db.state.forms.values()))
    filled = FilledForm.empty(__import__("uuid").uuid4(), form).apply(
        {
            "cedula": "1003895357",
            "titulo": "Un estudio",
            "anio_publicacion": 2025,
            "fecha_publicacion": "2025-03-14",
            "doi": "10.1234/abc.2025",
            "url": "https://example.org/articulo",
            "revista": "Revista de Pruebas",
            "issn": "1234-5678",
            "volumen": "12",
        }
    )
    assert filled.missing_for_submission() == ("soporte_articulo",)  # falta el soporte
    assert filled.with_attachments(frozenset({"soporte_articulo"})).missing_for_submission() == ()
    with pytest.raises(InvalidValue):
        filled.apply({"anio_publicacion": 1800})
