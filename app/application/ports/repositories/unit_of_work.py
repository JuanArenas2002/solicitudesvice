from collections.abc import Callable
from types import TracebackType
from typing import Protocol, Self

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


class UnitOfWork(Protocol):
    """Una transacción. Salir del `with` sin commit() (o con excepción) hace rollback."""

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

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...


UnitOfWorkFactory = Callable[[], UnitOfWork]
