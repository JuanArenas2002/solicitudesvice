from types import TracebackType
from typing import Self

from sqlalchemy.orm import Session, sessionmaker

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
from app.infrastructure.database.repositories.answers import SqlAlchemyRequestAnswerRepository
from app.infrastructure.database.repositories.assignments import (
    SqlAlchemyProductAssignmentRepository,
)
from app.infrastructure.database.repositories.attachments import (
    SqlAlchemyAttachmentRepository,
)
from app.infrastructure.database.repositories.audit import SqlAlchemyAuditLogRepository
from app.infrastructure.database.repositories.forms import SqlAlchemyFormRepository
from app.infrastructure.database.repositories.history import SqlAlchemyStatusHistoryRepository
from app.infrastructure.database.repositories.notifications import (
    SqlAlchemyNotificationRepository,
)
from app.infrastructure.database.repositories.product_types import SqlAlchemyProductTypeRepository
from app.infrastructure.database.repositories.request_numbers import (
    SqlAlchemyRequestNumberGenerator,
)
from app.infrastructure.database.repositories.requests import SqlAlchemyRequestRepository
from app.infrastructure.database.repositories.sessions import SqlAlchemyAuthSessionRepository
from app.infrastructure.database.repositories.storage_folders import (
    SqlAlchemyStorageFolderRepository,
)
from app.infrastructure.database.repositories.users import SqlAlchemyUserRepository


class SqlAlchemyUnitOfWork:
    """Una transacción PostgreSQL. Sin commit() explícito (o con excepción) se hace rollback."""

    users: UserRepository
    sessions: AuthSessionRepository
    audit: AuditLogRepository
    request_numbers: RequestNumberGenerator
    product_types: ProductTypeRepository
    forms: FormRepository
    requests: ResearchProductRequestRepository
    answers: RequestAnswerRepository
    history: RequestStatusHistoryRepository
    attachments: AttachmentRepository
    folders: StorageFolderRepository
    assignments: ProductAssignmentRepository
    notifications: NotificationRepository

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None

    def __enter__(self) -> Self:
        session = self._session_factory()
        self._session = session
        self.users = SqlAlchemyUserRepository(session)
        self.sessions = SqlAlchemyAuthSessionRepository(session)
        self.audit = SqlAlchemyAuditLogRepository(session)
        self.request_numbers = SqlAlchemyRequestNumberGenerator(session)
        self.product_types = SqlAlchemyProductTypeRepository(session)
        self.forms = SqlAlchemyFormRepository(session)
        self.requests = SqlAlchemyRequestRepository(session)
        self.answers = SqlAlchemyRequestAnswerRepository(session)
        self.history = SqlAlchemyStatusHistoryRepository(session)
        self.attachments = SqlAlchemyAttachmentRepository(session)
        self.folders = SqlAlchemyStorageFolderRepository(session)
        self.assignments = SqlAlchemyProductAssignmentRepository(session)
        self.notifications = SqlAlchemyNotificationRepository(session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._session is not None:
            self._session.rollback()  # no-op si ya se confirmó
            self._session.close()
            self._session = None

    def commit(self) -> None:
        if self._session is None:
            raise RuntimeError("commit() fuera de un bloque with")
        self._session.commit()
