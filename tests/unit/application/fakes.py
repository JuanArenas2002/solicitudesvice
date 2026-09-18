"""Dobles en memoria de los puertos: permiten probar los casos de uso sin base de datos.

FakeUnitOfWork imita la transacción real: trabaja sobre una COPIA del estado y solo la publica en
commit(); una excepción (o salir sin commit) descarta todo, igual que un rollback.
"""

import copy
from collections.abc import Collection, Iterator
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from types import TracebackType
from typing import Self
from uuid import UUID

from app.application.dto.forms import FormVersionSummary
from app.application.dto.page import Page, PageRequest
from app.application.dto.requests import RequestSummary
from app.application.ports.repositories.answers import RequestAnswerRepository
from app.application.ports.repositories.assignments import ProductAssignmentRepository
from app.application.ports.repositories.attachments import AttachmentRepository
from app.application.ports.repositories.audit import AuditLogRepository
from app.application.ports.repositories.forms import FormRepository
from app.application.ports.repositories.history import RequestStatusHistoryRepository
from app.application.ports.repositories.notifications import NotificationRepository
from app.application.ports.repositories.product_types import ProductTypeRepository
from app.application.ports.repositories.request_numbers import RequestNumberGenerator
from app.application.ports.repositories.requests import ResearchProductRequestRepository
from app.application.ports.repositories.sessions import AuthSessionRepository
from app.application.ports.repositories.storage_folders import StorageFolderRepository
from app.application.ports.repositories.users import UserRepository
from app.application.ports.services.journals import Journal
from app.application.ports.services.security import AccessClaims, AccessToken
from app.application.queries.requests import RequestFilter
from app.application.queries.users import UserFilter
from app.domain.entities.attachment import Attachment
from app.domain.entities.audit_entry import AuditEntry
from app.domain.entities.auth_session import AuthSession, RefreshToken
from app.domain.entities.notification import Notification
from app.domain.entities.product_type import ProductType
from app.domain.entities.research_product_request import ResearchProductRequest
from app.domain.entities.status_change import StatusChange
from app.domain.entities.storage_folder import StorageFolder
from app.domain.entities.user import User
from app.domain.enums.form_status import FormStatus
from app.domain.enums.request_status import RequestStatus
from app.domain.exceptions.errors import (
    DuplicateEmail,
    DuplicateProductType,
    FormDraftExists,
    JournalServiceUnavailable,
    Unauthorized,
)
from app.domain.forms.definition import FormField, FormOption, FormSection, FormVersion
from app.domain.forms.field_types import AnswerValue
from app.domain.forms.filled_form import FilledForm
from app.domain.services.access_policy import RequestScope
from app.domain.value_objects.email import Email
from app.domain.value_objects.request_number import RequestNumber

START = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)


class FakeClock:
    def __init__(self) -> None:
        self.current = START

    def now(self) -> datetime:
        return self.current

    def advance(self, **delta: float) -> None:
        self.current += timedelta(**delta)


class FakeHasher:
    def __init__(self) -> None:
        self.rehash_needed = False
        self.dummy_calls = 0

    def hash(self, password: str) -> str:
        return f"hash::{password}"

    def verify(self, password_hash: str, password: str) -> bool:
        return password_hash == f"hash::{password}"

    def needs_rehash(self, password_hash: str) -> bool:
        return self.rehash_needed

    def verify_dummy(self, password: str) -> None:
        self.dummy_calls += 1


class FakeAccessTokens:
    """Token = 'usuario|sesión'. La expiración real del JWT se prueba en el adaptador."""

    def issue(self, user_id: UUID, session_id: UUID, now: datetime) -> AccessToken:
        return AccessToken(f"{user_id}|{session_id}", now + timedelta(minutes=15))

    def decode(self, token: str) -> AccessClaims:
        try:
            user_id, session_id = token.split("|")
            return AccessClaims(UUID(user_id), UUID(session_id))
        except ValueError as error:
            raise Unauthorized("Token inválido") from error


class FakeRefreshGenerator:
    def __init__(self) -> None:
        self._counter = 0

    def generate(self) -> str:
        self._counter += 1
        return f"refresh-{self._counter}"

    def hash(self, raw_token: str) -> str:
        return f"sha::{raw_token}"


@dataclass
class State:
    users: dict[UUID, User] = field(default_factory=dict)
    sessions: dict[UUID, AuthSession] = field(default_factory=dict)
    tokens: dict[str, RefreshToken] = field(default_factory=dict)
    audit: list[AuditEntry] = field(default_factory=list)
    counters: dict[int, int] = field(default_factory=dict)
    product_types: dict[int, ProductType] = field(default_factory=dict)
    forms: dict[int, FormVersion] = field(default_factory=dict)
    next_id: int = 1  # ids enteros que en la BD asigna la identidad
    requests: dict[UUID, ResearchProductRequest] = field(default_factory=dict)
    answers: dict[UUID, dict[str, AnswerValue]] = field(default_factory=dict)
    history: list[StatusChange] = field(default_factory=list)
    attachments: dict[UUID, Attachment] = field(default_factory=dict)
    folders: dict[UUID, StorageFolder] = field(default_factory=dict)
    assignments: dict[UUID, set[int]] = field(default_factory=dict)
    notifications: list[Notification] = field(default_factory=list)
    folder_counters: dict[tuple[str, int], int] = field(default_factory=dict)


class InMemoryDatabase:
    def __init__(self) -> None:
        self.state = State()


class FakeUserRepository:
    def __init__(self, state: State) -> None:
        self._s = state

    def get(self, user_id: UUID) -> User | None:
        user = self._s.users.get(user_id)
        return copy.deepcopy(user) if user else None

    def get_by_email(self, email: Email) -> User | None:
        found = next((u for u in self._s.users.values() if u.email == email), None)
        return copy.deepcopy(found) if found else None

    def _check_email(self, user: User) -> None:
        if any(u.email == user.email and u.id != user.id for u in self._s.users.values()):
            raise DuplicateEmail("Ya existe un usuario con ese email")

    def add(self, user: User) -> None:
        self._check_email(user)
        self._s.users[user.id] = copy.deepcopy(user)

    def save(self, user: User) -> None:
        self._check_email(user)
        self._s.users[user.id] = copy.deepcopy(user)

    def list(self, filters: UserFilter, page: PageRequest) -> Page[User]:
        rows = list(self._s.users.values())
        if filters.role is not None:
            rows = [u for u in rows if u.role is filters.role]
        if filters.is_active is not None:
            rows = [u for u in rows if u.is_active == filters.is_active]
        if filters.search and filters.search.strip():
            term = filters.search.strip().lower()
            rows = [
                u for u in rows if term in f"{u.first_name} {u.last_name} {u.email.value}".lower()
            ]
        rows.sort(key=lambda u: (u.last_name, u.first_name, str(u.id)))
        window = rows[page.offset : page.offset + page.limit]
        return Page(tuple(copy.deepcopy(window)), len(rows), page.page, page.page_size)


class FakeSessionRepository:
    def __init__(self, state: State) -> None:
        self._s = state

    def add_session(self, session: AuthSession) -> None:
        self._s.sessions[session.id] = copy.deepcopy(session)

    def get_session(self, session_id: UUID) -> AuthSession | None:
        found = self._s.sessions.get(session_id)
        return copy.deepcopy(found) if found else None

    def save_session(self, session: AuthSession) -> None:
        self._s.sessions[session.id] = copy.deepcopy(session)

    def add_refresh_token(self, token: RefreshToken) -> None:
        self._s.tokens[token.token_hash] = copy.deepcopy(token)

    def get_refresh_token_for_update(self, token_hash: str) -> RefreshToken | None:
        found = self._s.tokens.get(token_hash)
        return copy.deepcopy(found) if found else None

    def save_refresh_token(self, token: RefreshToken) -> None:
        self._s.tokens[token.token_hash] = copy.deepcopy(token)

    def revoke_all_for_user(
        self, user_id: UUID, now: datetime, reason: str, except_session_id: UUID | None = None
    ) -> int:
        count = 0
        for session in self._s.sessions.values():
            if (
                session.user_id == user_id
                and session.revoked_at is None
                and session.id != except_session_id
            ):
                session.revoke(now, reason)
                count += 1
        return count


class FakeAuditRepository:
    def __init__(self, state: State) -> None:
        self._s = state

    def add(self, entry: AuditEntry) -> None:
        self._s.audit.append(entry)


class FakeRequestNumbers:
    def __init__(self, state: State) -> None:
        self._s = state

    def next(self, year: int) -> RequestNumber:
        self._s.counters[year] = self._s.counters.get(year, 0) + 1
        return RequestNumber(year, self._s.counters[year])


def _assign_ids(state: State, version: FormVersion) -> FormVersion:
    """Imita la BD: asigna ids enteros a versión, secciones, campos y opciones nuevos."""

    def take() -> int:
        state.next_id += 1
        return state.next_id - 1

    return FormVersion(
        id=version.id or take(),
        product_type_id=version.product_type_id,
        version_number=version.version_number,
        created_at=version.created_at,
        status=version.status,
        created_by=version.created_by,
        published_at=version.published_at,
        retired_at=version.retired_at,
        sections=tuple(
            FormSection(
                id=section.id or take(),
                title=section.title,
                description=section.description,
                fields=tuple(
                    FormField(
                        id=f.id or take(),
                        key=f.key,
                        label=f.label,
                        type_code=f.type_code,
                        required_to_submit=f.required_to_submit,
                        help_text=f.help_text,
                        min_length=f.min_length,
                        max_length=f.max_length,
                        min_value=f.min_value,
                        max_value=f.max_value,
                        options=tuple(
                            FormOption(o.value, o.label, o.id or take()) for o in f.options
                        ),
                        allowed_types=f.allowed_types,
                    )
                    for f in section.fields
                ),
            )
            for section in version.sections
        ),
    )


class FakeProductTypeRepository:
    def __init__(self, state: State) -> None:
        self._s = state

    def get(self, product_type_id: int) -> ProductType | None:
        found = self._s.product_types.get(product_type_id)
        return copy.deepcopy(found) if found else None

    def get_by_code(self, code: str) -> ProductType | None:
        found = next((p for p in self._s.product_types.values() if p.code == code), None)
        return copy.deepcopy(found) if found else None

    def add(self, product_type: ProductType) -> None:
        if any(p.code == product_type.code for p in self._s.product_types.values()):
            raise DuplicateProductType("Ya existe un producto con ese código")
        product_type.id = self._s.next_id
        self._s.next_id += 1
        self._s.product_types[product_type.id] = copy.deepcopy(product_type)

    def save(self, product_type: ProductType) -> None:
        assert product_type.id is not None
        self._s.product_types[product_type.id] = copy.deepcopy(product_type)

    def list(self, only_active: bool, page: PageRequest) -> Page[ProductType]:
        rows = [p for p in self._s.product_types.values() if p.is_active or not only_active]
        rows.sort(key=lambda p: (p.name, p.id or 0))
        window = rows[page.offset : page.offset + page.limit]
        return Page(tuple(copy.deepcopy(window)), len(rows), page.page, page.page_size)


class FakeFormRepository:
    def __init__(self, state: State) -> None:
        self._s = state

    def _find(self, product_type_id: int, status: FormStatus) -> FormVersion | None:
        found = next(
            (
                v
                for v in self._s.forms.values()
                if v.product_type_id == product_type_id and v.status is status
            ),
            None,
        )
        return copy.deepcopy(found) if found else None

    def get(self, version_id: int, *, for_update: bool = False) -> FormVersion | None:
        found = self._s.forms.get(version_id)
        return copy.deepcopy(found) if found else None

    def get_published(
        self, product_type_id: int, *, for_update: bool = False
    ) -> FormVersion | None:
        return self._find(product_type_id, FormStatus.PUBLICADA)

    def get_draft(self, product_type_id: int, *, for_update: bool = False) -> FormVersion | None:
        return self._find(product_type_id, FormStatus.BORRADOR)

    def list_versions(self, product_type_id: int) -> list[FormVersionSummary]:
        versions = sorted(
            (v for v in self._s.forms.values() if v.product_type_id == product_type_id),
            key=lambda v: -v.version_number,
        )
        return [
            FormVersionSummary(
                v.id or 0, v.version_number, v.status, v.created_at, v.published_at, v.retired_at
            )
            for v in versions
        ]

    def next_version_number(self, product_type_id: int) -> int:
        numbers = [
            v.version_number for v in self._s.forms.values() if v.product_type_id == product_type_id
        ]
        return max(numbers, default=0) + 1

    def _check_unique(self, version: FormVersion) -> None:
        """Imita los índices únicos: un borrador y una publicada por producto."""
        for other in self._s.forms.values():
            if other.product_type_id != version.product_type_id or other.id == version.id:
                continue
            if other.version_number == version.version_number or (
                other.status is FormStatus.BORRADOR and version.status is FormStatus.BORRADOR
            ):
                raise FormDraftExists("Ya existe un borrador")
            if other.status is FormStatus.PUBLICADA and version.status is FormStatus.PUBLICADA:
                raise RuntimeError("Solo puede haber una versión publicada por producto")

    def add(self, version: FormVersion) -> FormVersion:
        self._check_unique(version)
        saved = _assign_ids(self._s, version)
        assert saved.id is not None
        self._s.forms[saved.id] = copy.deepcopy(saved)
        return copy.deepcopy(saved)

    def save(self, version: FormVersion) -> FormVersion:
        assert version.id is not None
        self._check_unique(version)
        stored = self._s.forms[version.id]
        if stored.status is FormStatus.BORRADOR:  # un borrador se guarda con su estructura
            saved = _assign_ids(self._s, version)
        else:  # publicada/retirada: la estructura no cambia, solo estado y fechas
            saved = copy.deepcopy(stored)
            saved.status = version.status
            saved.published_at = version.published_at
            saved.retired_at = version.retired_at
        self._s.forms[version.id] = copy.deepcopy(saved)
        return copy.deepcopy(saved)


class FakeRequestRepository:
    def __init__(self, state: State) -> None:
        self._s = state

    def add(self, request: ResearchProductRequest) -> None:
        request.version = 1
        self._s.requests[request.id] = copy.deepcopy(request)

    def get(self, request_id: UUID, *, for_update: bool = False) -> ResearchProductRequest | None:
        found = self._s.requests.get(request_id)
        return copy.deepcopy(found) if found else None

    def save(self, request: ResearchProductRequest) -> None:
        stored = self._s.requests[request.id]
        request.version = stored.version + 1  # imita el optimistic locking de la BD
        self._s.requests[request.id] = copy.deepcopy(request)

    def search(
        self, scope: RequestScope, filters: RequestFilter, page: PageRequest
    ) -> Page[RequestSummary]:
        rows = []
        for r in self._s.requests.values():
            if scope.mentor_id is not None and r.mentor_id != scope.mentor_id:
                continue
            if not scope.include_drafts and r.status is RequestStatus.BORRADOR:
                continue
            if scope.product_ids is not None and r.product_type_id not in scope.product_ids:
                continue
            if filters.status is not None and r.status is not filters.status:
                continue
            if filters.mentor_id is not None and r.mentor_id != filters.mentor_id:
                continue
            form = self._s.forms[r.form_version_id]
            if (
                filters.product_type_id is not None
                and form.product_type_id != filters.product_type_id
            ):
                continue
            if filters.date_from is not None and r.created_at.date() < filters.date_from:
                continue
            if filters.date_to is not None and r.created_at.date() > filters.date_to:
                continue
            if filters.request_number and not str(r.request_number).startswith(
                filters.request_number.strip().upper()
            ):
                continue
            mentor = self._s.users[r.mentor_id]
            product = self._s.product_types[form.product_type_id]
            rows.append(
                RequestSummary(
                    id=r.id,
                    request_number=str(r.request_number),
                    mentor_id=r.mentor_id,
                    mentor_name=f"{mentor.first_name} {mentor.last_name}",
                    product_type_id=form.product_type_id,
                    product_type_code=product.code,
                    product_type_name=product.name,
                    form_version_id=r.form_version_id,
                    status=r.status,
                    version=r.version,
                    created_at=r.created_at,
                    updated_at=r.updated_at,
                    submitted_at=r.submitted_at,
                    reviewed_at=r.reviewed_at,
                )
            )
        rows.sort(key=lambda x: (x.created_at, str(x.id)), reverse=True)
        window = rows[page.offset : page.offset + page.limit]
        return Page(tuple(window), len(rows), page.page, page.page_size)


class FakeAnswerRepository:
    def __init__(self, state: State) -> None:
        self._s = state

    def load(self, request_id: UUID, form: FormVersion) -> FilledForm:
        return FilledForm(request_id, form, dict(self._s.answers.get(request_id, {})))

    def replace(self, filled: FilledForm) -> None:
        self._s.answers[filled.request_id] = dict(filled.answers)


class FakeHistoryRepository:
    def __init__(self, state: State) -> None:
        self._s = state

    def add(self, change: StatusChange) -> None:
        self._s.history.append(change)

    def list(self, request_id: UUID) -> list[StatusChange]:
        return [c for c in self._s.history if c.request_id == request_id]


class FakeAttachmentRepository:
    def __init__(self, state: State) -> None:
        self._s = state

    def add(self, attachment: Attachment) -> None:
        self._s.attachments[attachment.id] = attachment

    def get(self, request_id: UUID, attachment_id: UUID) -> Attachment | None:
        found = self._s.attachments.get(attachment_id)
        return found if found and found.request_id == request_id else None

    def list(self, request_id: UUID) -> list[Attachment]:
        rows = [a for a in self._s.attachments.values() if a.request_id == request_id]
        return sorted(rows, key=lambda a: a.created_at)

    def delete(self, attachment_id: UUID) -> None:
        self._s.attachments.pop(attachment_id, None)


class FakeAssignmentRepository:
    def __init__(self, state: State) -> None:
        self._s = state

    def product_ids(self, user_id: UUID) -> frozenset[int]:
        return frozenset(self._s.assignments.get(user_id, set()))

    def all(self) -> dict[UUID, frozenset[int]]:
        return {u: frozenset(ids) for u, ids in self._s.assignments.items() if ids}

    def replace(self, user_id: UUID, product_ids: Collection[int]) -> None:
        self._s.assignments[user_id] = set(product_ids)


class FakeJournalCatalog:
    """Catálogo de revistas en memoria: `known` son los ISSN que existen; `down` simula caída."""

    def __init__(self, known: dict[str, str] | None = None) -> None:
        self.known = known if known is not None else {"1234-5679": "Revista de Pruebas"}
        self.down = False
        self.calls: list[str] = []

    def find(self, issn: str) -> Journal | None:
        self.calls.append(issn)
        if self.down:
            raise JournalServiceUnavailable("caído")
        title = self.known.get(issn)
        return Journal(title, "Editorial", "Colombia", issn, None, True) if title else None


class FakeNotificationRepository:
    def __init__(self, state: State) -> None:
        self._s = state

    def add(self, notification: Notification) -> None:
        self._s.notifications.append(notification)

    def list(self, user_id: UUID, unread_only: bool, page: PageRequest) -> Page[Notification]:
        rows = [
            n
            for n in self._s.notifications
            if n.user_id == user_id and not (unread_only and n.is_read)
        ]
        rows.reverse()  # el reloj falso no avanza: el orden de llegada hace de fecha
        window = rows[page.offset : page.offset + page.limit]
        return Page(tuple(window), len(rows), page.page, page.page_size)

    def unread_count(self, user_id: UUID) -> int:
        return sum(1 for n in self._s.notifications if n.user_id == user_id and not n.is_read)

    def mark_read(self, user_id: UUID, ids: Collection[UUID] | None, now: datetime) -> int:
        changed = 0
        for i, n in enumerate(self._s.notifications):
            if n.user_id == user_id and not n.is_read and (ids is None or n.id in ids):
                self._s.notifications[i] = replace(n, read_at=now)
                changed += 1
        return changed


class FakeFolderRepository:
    def __init__(self, state: State) -> None:
        self._s = state

    def get(self, request_id: UUID) -> StorageFolder | None:
        return self._s.folders.get(request_id)

    def create(
        self,
        request_id: UUID,
        cedula: str,
        product_type_id: int,
        product_folder: str,
        now: datetime,
    ) -> StorageFolder:
        key = (cedula, product_type_id)
        self._s.folder_counters[key] = self._s.folder_counters.get(key, 0) + 1
        folder = StorageFolder(
            request_id, cedula, product_folder, self._s.folder_counters[key], now
        )
        self._s.folders[request_id] = folder
        return folder


class FakeFileStorage:
    """Almacén en memoria; `fail_on_save` simula un disco que falla."""

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.fail_on_save = False

    def save(self, key: str, content: bytes) -> None:
        if self.fail_on_save:
            raise OSError("disco lleno")
        self.files[key] = content

    def open(self, key: str) -> Iterator[bytes]:
        if key not in self.files:
            raise FileNotFoundError(key)  # como el real: falla al abrir, no al iterar
        return iter([self.files[key]])

    def delete(self, key: str) -> None:
        self.files.pop(key, None)


class FakeUnitOfWork:
    def __init__(self, database: InMemoryDatabase) -> None:
        self._database = database
        self._work: State | None = None
        self.users: UserRepository
        self.sessions: AuthSessionRepository
        self.audit: AuditLogRepository
        self.request_numbers: RequestNumberGenerator
        self.product_types: ProductTypeRepository
        self.forms: FormRepository
        self.requests: ResearchProductRequestRepository
        self.answers: RequestAnswerRepository
        self.history: RequestStatusHistoryRepository
        self.attachments: AttachmentRepository
        self.folders: StorageFolderRepository
        self.assignments: ProductAssignmentRepository
        self.notifications: NotificationRepository

    def __enter__(self) -> Self:
        work = copy.deepcopy(self._database.state)
        self._work = work
        self.users = FakeUserRepository(work)
        self.sessions = FakeSessionRepository(work)
        self.audit = FakeAuditRepository(work)
        self.request_numbers = FakeRequestNumbers(work)
        self.product_types = FakeProductTypeRepository(work)
        self.forms = FakeFormRepository(work)
        self.requests = FakeRequestRepository(work)
        self.answers = FakeAnswerRepository(work)
        self.history = FakeHistoryRepository(work)
        self.attachments = FakeAttachmentRepository(work)
        self.folders = FakeFolderRepository(work)
        self.assignments = FakeAssignmentRepository(work)
        self.notifications = FakeNotificationRepository(work)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._work = None  # lo no confirmado se descarta (rollback)

    def commit(self) -> None:
        assert self._work is not None
        self._database.state = copy.deepcopy(self._work)
