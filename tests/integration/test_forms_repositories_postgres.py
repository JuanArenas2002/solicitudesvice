"""Repositorios de formularios, casos de uso, concurrencia, carga inicial y CLI (PostgreSQL)."""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.application.commands.context import RequestContext
from app.application.commands.forms import (
    CreateProductTypeCommand,
    ReplaceFormDraftCommand,
    UpdateProductTypeCommand,
)
from app.application.dto.page import PageRequest
from app.application.use_cases.forms.manage_forms import (
    CreateFormDraft,
    GetPublishedForm,
    ListFormVersions,
    PublishForm,
    ReplaceFormDraft,
)
from app.application.use_cases.forms.manage_product_types import (
    CreateProductType,
    ListProductTypes,
    UpdateProductType,
)
from app.application.use_cases.forms.seed_default_forms import SeedDefaultForms
from app.domain.entities.product_type import ProductType
from app.domain.entities.user import User
from app.domain.enums.form_status import FormStatus
from app.domain.enums.role import Role
from app.domain.exceptions.errors import (
    DuplicateProductType,
    FormDraftExists,
    FormNotEditable,
    InvalidValue,
)
from app.domain.forms.definition import FormVersion, SectionInput
from app.domain.forms.filled_form import FilledForm
from app.domain.value_objects.actor import Actor
from app.infrastructure.clock import SystemClock
from app.infrastructure.database.models import (
    AuditLogModel,
    FormFieldModel,
    FormFieldOptionModel,
    FormSectionModel,
    FormVersionModel,
    ProductTypeModel,
)
from app.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork

pytestmark = pytest.mark.integration

CTX = RequestContext(correlation_id="it-forms", ip_address="198.51.100.7")
NOW = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)

BOOK: list[SectionInput] = [
    {
        "title": "Datos del libro",
        "description": "Información básica",
        "fields": [
            {"key": "cedula", "label": "Cédula", "type": "CEDULA", "required_to_submit": True},
            {
                "key": "titulo",
                "label": "Título",
                "type": "TEXT",
                "required_to_submit": True,
                "help_text": "Título completo",
                "min_length": 3,
                "max_length": 200,
            },
            {
                "key": "paginas",
                "label": "Páginas",
                "type": "DECIMAL",
                "min_value": "1.5",
                "max_value": 5000,
            },
            {
                "key": "idioma",
                "label": "Idioma",
                "type": "SINGLE_SELECT",
                "options": [
                    {"value": "es", "label": "Español"},
                    {"value": "en", "label": "Inglés"},
                    {"value": "fr", "label": "Francés"},
                ],
            },
        ],
    },
    {"title": "Editorial", "fields": [{"key": "editorial", "label": "Editorial", "type": "TEXT"}]},
]


class Stack:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory
        self.uow = lambda: SqlAlchemyUnitOfWork(session_factory)
        self.clock = SystemClock()

    def admin(self, role: Role = Role.ADMIN) -> Actor:
        user = User.create(
            first_name="Root",
            last_name="Admin",
            email=f"{uuid.uuid4().hex}@example.org",
            password_hash="$argon2id$x",
            role=role,
            now=self.clock.now(),
        )
        with self.uow() as uow:
            uow.users.add(user)
            uow.commit()
        return Actor(user.id, role)

    def create_type(self, actor: Actor, code: str = "LIBRO") -> tuple[ProductType, FormVersion]:
        return CreateProductType(self.uow, self.clock).execute(
            actor, CreateProductTypeCommand(code, "Libro"), CTX
        )

    def save(self, actor: Actor, version_id: int, sections: list[SectionInput]) -> FormVersion:
        return ReplaceFormDraft(self.uow, self.clock).execute(
            actor, ReplaceFormDraftCommand(version_id, sections), CTX
        )

    def publish(self, actor: Actor, version_id: int) -> FormVersion:
        return PublishForm(self.uow, self.clock).execute(actor, version_id, CTX)

    def count(self, model: type) -> int:
        with self.session_factory() as session:
            return session.scalar(select(func.count()).select_from(model)) or 0


@pytest.fixture
def stack(session_factory: sessionmaker[Session]) -> Stack:
    return Stack(session_factory)


def outline(version: FormVersion) -> list[tuple[object, ...]]:
    """Estructura sin ids, para comparar lo guardado con lo enviado."""
    return [
        (
            s.title,
            s.description,
            [
                (
                    f.key,
                    f.label,
                    f.type_code,
                    f.required_to_submit,
                    f.help_text,
                    f.min_length,
                    f.max_length,
                    f.min_value,
                    f.max_value,
                    [(o.value, o.label) for o in f.options],
                )
                for f in s.fields
            ],
        )
        for s in version.sections
    ]


# ---------------- tipos de producto ----------------
def test_product_type_repository_roundtrip(stack: Stack) -> None:
    with stack.uow() as uow:
        book = ProductType.create("LIBRO", "Libro", "Libros de investigación", NOW)
        patent = ProductType.create("PATENTE", "Patente", None, NOW)
        for pt in (book, patent):
            uow.product_types.add(pt)
        assert book.id is not None and patent.id is not None and book.id != patent.id
        patent.update(NOW, is_active=False)
        uow.product_types.save(patent)
        uow.commit()

    with stack.uow() as uow:
        loaded = uow.product_types.get_by_code("LIBRO")
        assert loaded is not None and loaded.description == "Libros de investigación"
        assert uow.product_types.get(loaded.id or 0) is not None
        assert uow.product_types.get_by_code("NADA") is None
        assert [p.code for p in uow.product_types.list(False, PageRequest()).items] == [
            "LIBRO",
            "PATENTE",
        ]
        active = uow.product_types.list(True, PageRequest())
        assert [p.code for p in active.items] == ["LIBRO"] and active.total == 1
        assert uow.product_types.list(False, PageRequest(2, 1)).items[0].code == "PATENTE"


def test_duplicate_product_code_is_a_domain_error(stack: Stack) -> None:
    with stack.uow() as uow:
        uow.product_types.add(ProductType.create("LIBRO", "Libro", None, NOW))
        uow.commit()
    with stack.uow() as uow, pytest.raises(DuplicateProductType):
        uow.product_types.add(ProductType.create("LIBRO", "Otro", None, NOW))


# ---------------- versiones de formulario ----------------
def test_form_structure_roundtrips_exactly(stack: Stack) -> None:
    admin = stack.admin()
    product, draft = stack.create_type(admin)
    assert draft.id is not None
    saved = stack.save(admin, draft.id, BOOK)

    with stack.uow() as uow:
        loaded = uow.forms.get(draft.id)
    assert loaded is not None
    assert outline(loaded) == outline(saved)
    (s1, s2) = loaded.sections
    assert (s1.title, s1.description, s2.description) == (
        "Datos del libro",
        "Información básica",
        None,
    )
    cedula, titulo, paginas, idioma = s1.fields
    assert cedula.type_code == "CEDULA" and cedula.required_to_submit
    assert (titulo.min_length, titulo.max_length, titulo.help_text) == (3, 200, "Título completo")
    assert (paginas.min_value, paginas.max_value) == (Decimal("1.5"), Decimal("5000"))
    assert [o.value for o in idioma.options] == ["es", "en", "fr"]  # el orden se conserva
    ids = [
        s1.id,
        s2.id,
        cedula.id,
        titulo.id,
        paginas.id,
        idioma.id,
        *(o.id for o in idioma.options),
    ]
    assert all(i is not None for i in ids)


def test_saving_a_draft_replaces_its_structure_even_with_the_same_keys(stack: Stack) -> None:
    """Borrar y reinsertar claves iguales en un mismo guardado no debe chocar con los únicos."""
    admin = stack.admin()
    _, draft = stack.create_type(admin)
    assert draft.id is not None
    first = stack.save(admin, draft.id, BOOK)
    reordered: list[SectionInput] = [BOOK[1], BOOK[0]]  # mismas claves, otro orden
    second = stack.save(admin, draft.id, reordered)

    assert [s.title for s in second.sections] == ["Editorial", "Datos del libro"]
    old_ids = {f.id for f in first.fields()}
    assert old_ids.isdisjoint({f.id for f in second.fields()})  # filas nuevas
    assert stack.count(FormFieldModel) == 5 and stack.count(FormSectionModel) == 2
    assert stack.count(FormFieldOptionModel) == 3  # sin filas huérfanas


def test_empty_structure_removes_everything(stack: Stack) -> None:
    admin = stack.admin()
    _, draft = stack.create_type(admin)
    assert draft.id is not None
    stack.save(admin, draft.id, BOOK)
    stack.save(admin, draft.id, [])
    assert stack.count(FormFieldModel) == 0 and stack.count(FormSectionModel) == 0


def test_publish_keeps_the_saved_structure_and_sets_dates(stack: Stack) -> None:
    admin = stack.admin()
    product, draft = stack.create_type(admin)
    assert draft.id is not None and product.id is not None
    stack.save(admin, draft.id, BOOK)
    published = stack.publish(admin, draft.id)

    assert published.status is FormStatus.PUBLICADA and published.published_at is not None
    with stack.uow() as uow:
        assert uow.forms.get_draft(product.id) is None
        current = uow.forms.get_published(product.id)
    assert current is not None and outline(current) == outline(published)
    assert [f.key for f in current.fields()] == [
        "cedula",
        "titulo",
        "paginas",
        "idioma",
        "editorial",
    ]


def test_new_version_flow_keeps_history_and_a_single_published_form(stack: Stack) -> None:
    admin = stack.admin(Role.ADMINISTRATIVO)
    product, draft = stack.create_type(admin)
    assert draft.id is not None and product.id is not None
    stack.save(admin, draft.id, BOOK)
    v1 = stack.publish(admin, draft.id)

    v2_draft = CreateFormDraft(stack.uow, stack.clock).execute(admin, product.id, CTX)
    assert v2_draft.version_number == 2 and v2_draft.id != v1.id
    assert outline(v2_draft) == outline(v1)  # copia fiel de la publicada
    assert v2_draft.id is not None
    changed: list[SectionInput] = [
        {
            **BOOK[0],
            "fields": [*BOOK[0]["fields"], {"key": "isbn", "label": "ISBN", "type": "TEXT"}],
        },
        BOOK[1],
    ]
    stack.save(admin, v2_draft.id, changed)
    v2 = stack.publish(admin, v2_draft.id)

    versions = ListFormVersions(stack.uow).execute(admin, product.id)
    assert [(v.version_number, v.status) for v in versions] == [
        (2, FormStatus.PUBLICADA),
        (1, FormStatus.RETIRADA),
    ]
    assert versions[1].retired_at is not None
    with stack.uow() as uow:
        assert uow.forms.next_version_number(product.id) == 3
        assert uow.forms.get(v1.id or 0) is not None
        old = uow.forms.get(v1.id or 0)
        current = uow.forms.get_published(product.id)
    assert old is not None and old.status is FormStatus.RETIRADA
    assert "isbn" not in [f.key for f in old.fields()]  # la v1 conserva su estructura original
    assert (
        current is not None and current.id == v2.id and "isbn" in [f.key for f in current.fields()]
    )

    with pytest.raises(FormNotEditable):
        stack.save(admin, v1.id or 0, BOOK)  # una retirada tampoco se edita


def test_only_one_draft_per_product(stack: Stack) -> None:
    admin = stack.admin()
    product, _ = stack.create_type(admin)
    assert product.id is not None
    with pytest.raises(FormDraftExists):
        CreateFormDraft(stack.uow, stack.clock).execute(admin, product.id, CTX)
    with stack.uow() as uow, pytest.raises(FormDraftExists):
        uow.forms.add(FormVersion.new(product.id, 5, None, NOW))


def test_failed_validation_rolls_everything_back(stack: Stack) -> None:
    admin = stack.admin()
    _, draft = stack.create_type(admin)
    assert draft.id is not None
    stack.save(admin, draft.id, BOOK)
    with pytest.raises(InvalidValue):
        stack.save(
            admin,
            draft.id,
            [{"title": "X", "fields": [{"key": "a", "label": "A", "type": "NADA"}]}],
        )
    with stack.uow() as uow:
        stored = uow.forms.get(draft.id)
    assert stored is not None and len(list(stored.fields())) == 5  # el borrador quedó intacto


def test_duplicate_product_creation_leaves_no_form_or_audit_rows(stack: Stack) -> None:
    admin = stack.admin()
    stack.create_type(admin)
    audit_before, forms_before = stack.count(AuditLogModel), stack.count(FormVersionModel)
    with pytest.raises(DuplicateProductType):
        stack.create_type(admin)
    assert (stack.count(AuditLogModel), stack.count(FormVersionModel)) == (
        audit_before,
        forms_before,
    )
    assert stack.count(ProductTypeModel) == 1


def test_mentors_see_only_active_products_with_a_published_form(stack: Stack) -> None:
    admin = stack.admin()
    mentor = stack.admin(Role.MENTOR)
    product, draft = stack.create_type(admin)
    assert product.id is not None and draft.id is not None
    stack.save(admin, draft.id, BOOK)
    stack.publish(admin, draft.id)

    form = GetPublishedForm(stack.uow).execute(mentor, product.id)
    assert form.status is FormStatus.PUBLICADA
    UpdateProductType(stack.uow, stack.clock).execute(
        admin, UpdateProductTypeCommand(product.id, is_active=False), CTX
    )
    assert ListProductTypes(stack.uow).execute(mentor, PageRequest()).total == 0
    assert ListProductTypes(stack.uow).execute(admin, PageRequest()).total == 1


# ---------------- concurrencia ----------------
def test_two_admins_publishing_the_same_draft_only_one_succeeds(stack: Stack) -> None:
    admins = [stack.admin(), stack.admin(Role.ADMINISTRATIVO)]
    _, draft = stack.create_type(admins[0])
    assert draft.id is not None
    stack.save(admins[0], draft.id, BOOK)
    barrier = threading.Barrier(2)

    def attempt(actor: Actor) -> object:
        barrier.wait()
        try:
            return stack.publish(actor, draft.id or 0)
        except FormNotEditable as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, admins))
    assert sum(isinstance(o, FormVersion) for o in outcomes) == 1
    assert sum(isinstance(o, FormNotEditable) for o in outcomes) == 1
    with stack.session_factory() as session:
        published = session.scalars(
            select(FormVersionModel).where(FormVersionModel.status_id == 2)
        ).all()
        assert len(published) == 1


def test_two_admins_opening_a_draft_at_once_only_one_succeeds(stack: Stack) -> None:
    admins = [stack.admin(), stack.admin(Role.ADMINISTRATIVO)]
    product, draft = stack.create_type(admins[0])
    assert product.id is not None and draft.id is not None
    stack.save(admins[0], draft.id, BOOK)
    stack.publish(admins[0], draft.id)  # ahora no hay borrador y sí una publicada
    barrier = threading.Barrier(2)

    def attempt(actor: Actor) -> object:
        barrier.wait()
        try:
            return CreateFormDraft(stack.uow, stack.clock).execute(actor, product.id or 0, CTX)
        except FormDraftExists as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, admins))
    assert sum(isinstance(o, FormVersion) for o in outcomes) == 1
    assert sum(isinstance(o, FormDraftExists) for o in outcomes) == 1


# ---------------- formulario inicial y respuestas ----------------
def test_seed_loads_the_article_form_and_it_validates_answers(stack: Stack) -> None:
    admin = stack.admin()
    seed = SeedDefaultForms(stack.uow, stack.clock)
    assert seed.execute(admin, CTX) is True
    assert seed.execute(admin, CTX) is False

    with stack.uow() as uow:
        product = uow.product_types.get_by_code("ARTICULO")
        assert product is not None and product.id is not None
        assert product.folder_name == "Articulos"
        form = uow.forms.get_published(product.id)
    assert form is not None and form.status is FormStatus.PUBLICADA
    assert [s.title for s in form.sections] == [
        "Datos del artículo",
        "Datos de la revista",
        "Soportes",
    ]
    assert {f.key for f in form.fields() if f.required_to_submit} == {
        "cedula",
        "titulo",
        "anio_publicacion",
        "revista",
        "soporte_articulo",
    }
    year = form.field("anio_publicacion")
    assert year is not None and (year.min_value, year.max_value) == (Decimal(1900), Decimal(2100))

    filled = FilledForm.empty(uuid.uuid4(), form).apply(
        {
            "cedula": "1003895357",
            "titulo": "Un estudio",
            "anio_publicacion": 2025,
            "revista": "Revista",
            "doi": "10.1234/x",
        }
    )
    assert filled.missing_for_submission() == ("soporte_articulo",)
    assert filled.with_attachments(frozenset({"soporte_articulo"})).missing_for_submission() == ()
    with pytest.raises(InvalidValue):
        filled.apply({"anio_publicacion": 1800})


def test_seed_is_atomic_and_audited(stack: Stack) -> None:
    admin = stack.admin()
    SeedDefaultForms(stack.uow, stack.clock).execute(admin, CTX)
    assert stack.count(ProductTypeModel) == 1 and stack.count(FormVersionModel) == 1
    with stack.session_factory() as session:
        actions = session.scalars(select(AuditLogModel.action_id).order_by(AuditLogModel.id)).all()
    assert actions[-2:] == [22, 26]  # PRODUCT_TYPE_CREATED, FORM_PUBLISHED


def test_a_form_referenced_by_a_request_keeps_working_after_a_new_version(stack: Stack) -> None:
    """La versión que usa una solicitud queda retirada pero íntegra: sus campos siguen ahí."""
    admin = stack.admin()
    product, draft = stack.create_type(admin)
    assert product.id is not None and draft.id is not None
    stack.save(admin, draft.id, BOOK)
    v1 = stack.publish(admin, draft.id)
    v2_draft = CreateFormDraft(stack.uow, stack.clock).execute(admin, product.id, CTX)
    assert v2_draft.id is not None
    stack.save(admin, v2_draft.id, BOOK[:1])  # la v2 quita la sección "Editorial"
    stack.publish(admin, v2_draft.id)

    with stack.uow() as uow:
        old = uow.forms.get(v1.id or 0)
    assert old is not None and old.field("editorial") is not None  # aún existe para la solicitud
    filled = FilledForm.empty(uuid.uuid4(), old).apply({"titulo": "Libro", "editorial": "Acme"})
    assert dict(filled.answers) == {"titulo": "Libro", "editorial": "Acme"}
