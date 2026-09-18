from collections.abc import Collection
from dataclasses import dataclass
from uuid import UUID

from app.application.dto.page import Page, PageRequest
from app.application.ports.repositories.unit_of_work import UnitOfWorkFactory
from app.application.ports.services.clock import Clock
from app.domain.entities.notification import Notification
from app.domain.value_objects.actor import Actor


@dataclass(frozen=True, slots=True)
class NotificationList:
    page: Page[Notification]
    unread: int


class ListNotifications:
    """Las notificaciones del propio usuario (nunca las de otro)."""

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, actor: Actor, unread_only: bool, page: PageRequest) -> NotificationList:
        with self._uow_factory() as uow:
            return NotificationList(
                uow.notifications.list(actor.user_id, unread_only, page),
                uow.notifications.unread_count(actor.user_id),
            )


class CountUnreadNotifications:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, actor: Actor) -> int:
        with self._uow_factory() as uow:
            return uow.notifications.unread_count(actor.user_id)


class MarkNotificationsRead:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    def execute(self, actor: Actor, ids: Collection[UUID] | None) -> int:
        """ids=None marca todas. Los ids ajenos o inexistentes se ignoran (no revelan nada)."""
        with self._uow_factory() as uow:
            changed = uow.notifications.mark_read(actor.user_id, ids, self._clock.now())
            uow.commit()
            return changed
