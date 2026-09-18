"""Solicitudes de punta a punta contra PostgreSQL REAL: respuestas tipadas, ciclo de vida,
ownership, listados sin N+1 y concurrencia."""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.application.commands.context import RequestContext
from app.application.commands.forms import CreateProductTypeCommand, ReplaceFormDraftCommand
from app.application.dto.page import PageRequest
from app.application.dto.requests import RequestDetail
from app.application.queries.requests import RequestFilter
from app.application.use_cases.forms.manage_forms import (
    CreateFormDraft,
    PublishForm,
    ReplaceFormDraft,
)
from app.application.use_cases.forms.manage_product_types import CreateProductType
from app.application.use_cases.requests.commands import (
    ApproveRequest,
    CreateRequest,
    RejectRequest,
    RequestCorrection,
    ResubmitRequest,
    StartReview,
    SubmitRequest,
    UpdateAnswers,
)
from app.application.use_cases.requests.queries import (
    GetRequest,
    GetRequestHistory,
    ListCorrections,
    ListRequests,
)
from app.domain.entities.user import User
from app.domain.enums.request_status import RequestStatus as S
from app.domain.enums.role import Role
from app.domain.exceptions.errors import (
    ConcurrentModification,
    Forbidden,
    IncompleteProduct,
    InvalidStatusTransition,
    InvalidValue,
    RequestNotFound,
)
from app.domain.forms.definition import SectionInput
from app.domain.value_objects.actor import Actor
from app.infrastructure.clock import SystemClock
from app.infrastructure.database.models import (
    RequestAnswerModel,
    RequestStatusHistoryModel,
    ResearchProductRequestModel,
)
from app.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork

pytestmark = pytest.mark.integration

CTX = RequestContext(correlation_id="it-requests", ip_address="198.51.100.9")

EVERYTHING: list[SectionInput] = [
    {
        "title": "Todo",
        "fields": [
            {"key": "cedula", "label": "Cédula", "type": "CEDULA", "required_to_submit": True},
            {"key": "titulo", "label": "Título", "type": "TEXT", "required_to_submit": True},
            {
                "key": "anio",
                "label": "Año",
                "type": "INTEGER",
                "min_value": 1900,
                "max_value": 2100,
            },
            {"key": "importe", "label": "Importe", "type": "DECIMAL"},
            {"key": "fecha", "label": "Fecha", "type": "DATE"},
            {"key": "ok", "label": "¿Aplica?", "type": "BOOLEAN"},
            {
                "key": "idioma",
                "label": "Idioma",
                "type": "SINGLE_SELECT",
                "options": [{"value": "es", "label": "ES"}, {"value": "en", "label": "EN"}],
            },
            {
                "key": "etiquetas",
                "label": "Etiquetas",
                "type": "MULTI_SELECT",
                "options": [
                    {"value": "a", "label": "A"},
                    {"value": "b", "label": "B"},
                    {"value": "c", "label": "C"},
                ],
            },
            {"key": "doi", "label": "DOI", "type": "DOI"},
            {"key": "url", "label": "URL", "type": "URL"},
            {"key": "issn", "label": "ISSN", "type": "ISSN"},
            {"key": "correo", "label": "Correo", "type": "EMAIL"},
            {"key": "largo", "label": "Descripción", "type": "LONG_TEXT"},
            {"key": "soporte", "label": "Acta", "type": "SUPPORT", "allowed_types": ["pdf"]},
        ],
    }
]

CED = {"cedula": "1003895357"}

ALL_ANSWERS: dict[str, object] = {
    **CED,
    "titulo": "Un estudio",
    "anio": 2025,
    "importe": "1234.5678",
    "fecha": "2025-03-14",
    "ok": False,
    "idioma": "en",
    "etiquetas": ["c", "a"],
    "doi": "10.1234/abc.1",
    "url": "https://example.org/a",
    "issn": "1234-567x",
    "correo": "Ana@Example.org",
    "largo": "x" * 9000,
}


class World:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory
        self.uow = lambda: SqlAlchemyUnitOfWork(session_factory)
        self.clock = SystemClock()
        self.admin = self.user(Role.ADMIN)
        self.mentor = self.user(Role.MENTOR)
        self.other = self.user(Role.MENTOR)
        self.staff = self.user(Role.ADMINISTRATIVO)
        self.product_id = self.publish_product("TODO", EVERYTHING)

    def user(self, role: Role) -> Actor:
        user = User.create(
            first_name="Ana",
            last_name=role.value.title(),
            email=f"{uuid.uuid4().hex}@example.org",
            password_hash="$argon2id$x",
            role=role,
            now=self.clock.now(),
        )
        with self.uow() as uow:
            uow.users.add(user)
            uow.commit()
        return Actor(user.id, role)

    def publish_product(self, code: str, sections: list[SectionInput]) -> int:
        product, draft = CreateProductType(self.uow, self.clock).execute(
            self.admin, CreateProductTypeCommand(code, code.title()), CTX
        )
        assert product.id is not None and draft.id is not None
        ReplaceFormDraft(self.uow, self.clock).execute(
            self.admin, ReplaceFormDraftCommand(draft.id, sections), CTX
        )
        PublishForm(self.uow, self.clock).execute(self.admin, draft.id, CTX)
        return product.id

    # casos de uso
    def create(self, actor: Actor | None = None, product_id: int | None = None) -> RequestDetail:
        return CreateRequest(self.uow, self.clock).execute(
            actor or self.mentor, product_id or self.product_id, CTX
        )

    def update(
        self, detail: RequestDetail, changes: dict[str, object], actor: Actor | None = None
    ) -> RequestDetail:
        return UpdateAnswers(self.uow, self.clock).execute(
            actor or self.mentor, detail.request.id, changes, detail.request.version, CTX
        )

    def get(self, request_id: uuid.UUID, actor: Actor | None = None) -> RequestDetail:
        return GetRequest(self.uow).execute(actor or self.mentor, request_id)

    def submit(self, rid: uuid.UUID, actor: Actor | None = None) -> RequestDetail:
        return SubmitRequest(self.uow, self.clock).execute(actor or self.mentor, rid, CTX)

    def review(self, rid: uuid.UUID, actor: Actor | None = None) -> RequestDetail:
        return StartReview(self.uow, self.clock).execute(actor or self.staff, rid, CTX)

    def count(self, model: type) -> int:
        with self.session_factory() as session:
            return session.scalar(select(func.count()).select_from(model)) or 0


@pytest.fixture
def world(session_factory: sessionmaker[Session]) -> World:
    return World(session_factory)


# ---------------- respuestas tipadas ----------------
def test_every_field_type_roundtrips_through_postgres(world: World) -> None:
    detail = world.update(world.create(), ALL_ANSWERS)
    loaded = world.get(detail.request.id)

    assert dict(loaded.filled.answers) == {
        "cedula": "1003895357",
        "titulo": "Un estudio",
        "anio": 2025,
        "importe": Decimal("1234.5678"),
        "fecha": date(2025, 3, 14),
        "ok": False,  # False es una respuesta válida, distinta de "sin respuesta"
        "idioma": "en",
        "etiquetas": ("a", "c"),  # vuelven en el orden del formulario
        "doi": "10.1234/abc.1",
        "url": "https://example.org/a",
        "issn": "1234-567X",
        "correo": "ana@example.org",
        "largo": "x" * 9000,
    }
    assert isinstance(loaded.filled.answers["anio"], int)
    # una fila tipada por respuesta (multi-selección: una por opción)
    assert world.count(RequestAnswerModel) == 14


def test_replacing_and_clearing_answers_keeps_only_the_latest(world: World) -> None:
    detail = world.update(world.create(), ALL_ANSWERS)
    detail = world.update(
        detail, {"idioma": "es", "etiquetas": ["b"], "ok": True, "doi": None, "largo": ""}
    )
    detail = world.update(detail, {"etiquetas": ["a", "b", "c"], "titulo": "Otro"})

    answers = dict(world.get(detail.request.id).filled.answers)
    assert answers["idioma"] == "es" and answers["ok"] is True and answers["titulo"] == "Otro"
    assert answers["etiquetas"] == ("a", "b", "c")
    assert "doi" not in answers and "largo" not in answers
    assert world.count(RequestAnswerModel) == 13  # 10 campos simples + 3 opciones elegidas


def test_invalid_answers_are_rejected_before_touching_the_database(world: World) -> None:
    detail = world.update(world.create(), {**CED, "titulo": "Original"})
    rows = world.count(RequestAnswerModel)
    for bad in ({"anio": 1800}, {"idioma": "fr"}, {"etiquetas": ["a", "a"]}, {"fecha": "ayer"}):
        with pytest.raises(InvalidValue):
            world.update(detail, {**CED, "titulo": "Cambiado", **bad})
    assert dict(world.get(detail.request.id).filled.answers) == {**CED, "titulo": "Original"}
    assert world.count(RequestAnswerModel) == rows


# ---------------- ciclo de vida ----------------
def test_full_lifecycle_persists_history_corrections_and_versions(world: World) -> None:
    detail = world.update(world.create(), ALL_ANSWERS)
    rid = detail.request.id
    world.submit(rid)
    world.review(rid)
    RequestCorrection(world.uow, world.clock).execute(world.staff, rid, "Falta el DOI", CTX)

    editable = world.get(rid)
    world.update(editable, {"doi": "10.9999/nuevo"})  # en corrección el mentor edita
    ResubmitRequest(world.uow, world.clock).execute(world.mentor, rid, CTX)
    world.review(rid)
    approved = ApproveRequest(world.uow, world.clock).execute(world.staff, rid, "Bien", CTX)

    assert approved.request.status is S.APROBADA and approved.request.reviewed_at is not None
    assert approved.filled.answers["doi"] == "10.9999/nuevo"
    (correction,) = ListCorrections(world.uow).execute(world.mentor, rid)
    assert not correction.is_open and correction.resolved_at is not None
    history = GetRequestHistory(world.uow).execute(world.staff, rid)
    assert [(h.previous_status, h.new_status) for h in history] == [
        (None, S.BORRADOR),
        (S.BORRADOR, S.ENVIADA),
        (S.ENVIADA, S.EN_REVISION),
        (S.EN_REVISION, S.CORRECCION_SOLICITADA),
        (S.CORRECCION_SOLICITADA, S.REENVIADA),
        (S.REENVIADA, S.EN_REVISION),
        (S.EN_REVISION, S.APROBADA),
    ]
    assert history[3].reason == "Falta el DOI"
    assert approved.request.version > detail.request.version  # cada cambio subió la versión


def test_incomplete_submission_is_rejected_and_leaves_no_trace(world: World) -> None:
    detail = world.create()
    with pytest.raises(IncompleteProduct) as error:
        world.submit(detail.request.id)
    assert error.value.missing == ("cedula", "titulo")
    assert world.get(detail.request.id).request.status is S.BORRADOR
    assert world.count(RequestStatusHistoryModel) == 1  # solo el alta del borrador


def test_rejection_is_final(world: World) -> None:
    rid = world.update(world.create(), {**CED, "titulo": "T"}).request.id
    world.submit(rid)
    world.review(rid)
    RejectRequest(world.uow, world.clock).execute(world.staff, rid, "Fuera del alcance", CTX)
    with pytest.raises(InvalidStatusTransition):
        ApproveRequest(world.uow, world.clock).execute(world.staff, rid, None, CTX)


# ---------------- ownership y roles (con datos reales) ----------------
def test_ownership_and_roles_are_enforced_against_the_database(world: World) -> None:
    rid = world.update(world.create(), {**CED, "titulo": "T"}).request.id
    with pytest.raises(RequestNotFound):
        world.get(rid, world.other)  # otro mentor: 404, no 403
    with pytest.raises(RequestNotFound):
        world.get(rid, world.staff)  # el borrador es privado
    with pytest.raises(RequestNotFound):
        world.get(rid, world.admin)
    world.submit(rid)
    assert world.get(rid, world.staff).request.id == rid
    assert world.get(rid, world.admin).request.id == rid  # el admin solo lee
    with pytest.raises(Forbidden):
        world.review(rid, world.admin)
    with pytest.raises(Forbidden):
        world.review(rid, world.mentor)
    with pytest.raises(RequestNotFound):
        world.submit(rid, world.other)
    with pytest.raises(Forbidden):
        world.create(world.staff)


# ---------------- versiones de formulario ----------------
def test_a_request_keeps_its_form_version_after_a_new_one_is_published(world: World) -> None:
    detail = world.update(world.create(), {**CED, "titulo": "Con la v1", "correo": "a@b.co"})
    old_form_id = detail.request.form_version_id

    draft = CreateFormDraft(world.uow, world.clock).execute(world.admin, world.product_id, CTX)
    assert draft.id is not None
    slim: list[SectionInput] = [
        {
            "title": "v2",
            "fields": [
                {"key": "cedula", "label": "Cédula", "type": "CEDULA", "required_to_submit": True},
                {"key": "titulo", "label": "Título", "type": "TEXT"},
            ],
        }
    ]
    ReplaceFormDraft(world.uow, world.clock).execute(
        world.admin, ReplaceFormDraftCommand(draft.id, slim), CTX
    )
    PublishForm(world.uow, world.clock).execute(world.admin, draft.id, CTX)

    same = world.get(detail.request.id)
    assert same.request.form_version_id == old_form_id  # sigue con la versión con la que empezó
    assert same.filled.form.field("correo") is not None
    updated = world.update(same, {"correo": "otro@b.co"})  # y todavía puede usar campos de la v1
    assert updated.filled.answers["correo"] == "otro@b.co"
    fresh = world.create()
    assert fresh.request.form_version_id == draft.id and fresh.filled.form.field("correo") is None


# ---------------- listados ----------------
def test_listing_filters_and_scope_run_in_sql(world: World) -> None:
    mine_draft = world.create()
    sent = world.update(world.create(), {**CED, "titulo": "Enviada"})
    world.submit(sent.request.id)
    other_sent = world.update(world.create(world.other), {**CED, "titulo": "Ajena"}, world.other)
    world.submit(other_sent.request.id, world.other)

    lister = ListRequests(world.uow)
    mine = lister.execute(world.mentor, RequestFilter(), PageRequest())
    assert mine.total == 2 and {i.mentor_id for i in mine.items} == {world.mentor.user_id}
    assert mine_draft.request.id in {i.id for i in mine.items}
    spoof = lister.execute(
        world.mentor, RequestFilter(mentor_id=world.other.user_id), PageRequest()
    )
    assert spoof.total == 2  # no puede ver las ajenas por más que las pida

    for viewer in (world.staff, world.admin):
        page = lister.execute(viewer, RequestFilter(), PageRequest())
        assert page.total == 2 and all(i.status is S.ENVIADA for i in page.items)  # sin borradores
    staff_view = lister.execute(
        world.staff, RequestFilter(mentor_id=world.other.user_id), PageRequest()
    )
    assert [i.id for i in staff_view.items] == [other_sent.request.id]
    by_type = lister.execute(
        world.staff, RequestFilter(product_type_id=world.product_id), PageRequest()
    )
    assert by_type.total == 2
    assert lister.execute(world.staff, RequestFilter(product_type_id=999), PageRequest()).total == 0
    assert lister.execute(world.staff, RequestFilter(status=S.APROBADA), PageRequest()).total == 0
    number = str(sent.request.request_number)
    assert [
        i.id
        for i in lister.execute(
            world.staff, RequestFilter(request_number=number), PageRequest()
        ).items
    ] == [sent.request.id]
    assert lister.execute(world.staff, RequestFilter(request_number="%"), PageRequest()).total == 0
    today = date.today()
    assert (
        lister.execute(
            world.staff, RequestFilter(date_from=today, date_to=today), PageRequest()
        ).total
        == 2
    )
    assert (
        lister.execute(world.staff, RequestFilter(date_to=date(2000, 1, 1)), PageRequest()).total
        == 0
    )
    row = lister.execute(world.staff, RequestFilter(request_number=number), PageRequest()).items[0]
    assert (row.product_type_code, row.status, row.mentor_name) == ("TODO", S.ENVIADA, "Ana Mentor")


def test_listing_uses_a_constant_number_of_queries(
    world: World, session_factory: sessionmaker[Session]
) -> None:
    for _ in range(12):
        world.update(world.create(), {**CED, "titulo": "x"})
    statements: list[str] = []
    engine = session_factory.kw["bind"]

    def record(conn: object, cursor: object, statement: str, *rest: object) -> None:
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        page = ListRequests(world.uow).execute(world.mentor, RequestFilter(), PageRequest(1, 50))
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert page.total == 12 and len(page.items) == 12
    selects = [s for s in statements if s.lstrip().upper().startswith("SELECT")]
    assert len(selects) == 2  # un COUNT y un SELECT con JOIN: sin N+1


# ---------------- concurrencia ----------------
def test_double_approval_only_one_wins(world: World) -> None:
    rid = world.update(world.create(), {**CED, "titulo": "T"}).request.id
    world.submit(rid)
    world.review(rid)
    staff = [world.staff, world.user(Role.ADMINISTRATIVO)]
    barrier = threading.Barrier(2)

    def approve(actor: Actor) -> object:
        barrier.wait()
        try:
            return ApproveRequest(world.uow, world.clock).execute(actor, rid, None, CTX)
        except InvalidStatusTransition as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(approve, staff))
    assert sum(isinstance(o, RequestDetail) for o in outcomes) == 1
    assert sum(isinstance(o, InvalidStatusTransition) for o in outcomes) == 1
    with world.session_factory() as session:
        approvals = session.scalar(
            select(func.count())
            .select_from(RequestStatusHistoryModel)
            .where(RequestStatusHistoryModel.new_status_id == 6)
        )
    assert approvals == 1


def test_concurrent_edits_with_the_same_version_only_one_wins(world: World) -> None:
    detail = world.update(world.create(), {**CED, "titulo": "Base"})
    barrier = threading.Barrier(2)

    def edit(title: str) -> object:
        barrier.wait()
        try:
            return world.update(
                detail, {**CED, "titulo": title}
            )  # ambos parten de la misma versión
        except ConcurrentModification as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(edit, ["A", "B"]))
    assert sum(isinstance(o, RequestDetail) for o in outcomes) == 1
    assert sum(isinstance(o, ConcurrentModification) for o in outcomes) == 1


def test_concurrent_creations_get_unique_consecutive_numbers(world: World) -> None:
    mentors = [world.user(Role.MENTOR) for _ in range(8)]
    barrier = threading.Barrier(len(mentors))

    def create(actor: Actor) -> int:
        barrier.wait()
        return world.create(actor).request.request_number.sequence

    with ThreadPoolExecutor(max_workers=len(mentors)) as pool:
        numbers = sorted(pool.map(create, mentors))
    assert numbers == list(range(1, len(mentors) + 1))
    assert world.count(ResearchProductRequestModel) == len(mentors)
