from collections.abc import Collection
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.application.dto.page import Page, PageRequest
from app.domain.entities.notification import Notification


class NotificationRepository(Protocol):
    def add(self, notification: Notification) -> None: ...

    def list(self, user_id: UUID, unread_only: bool, page: PageRequest) -> Page[Notification]:
        """Solo las del usuario, de la más reciente a la más antigua."""
        ...

    def unread_count(self, user_id: UUID) -> int: ...

    def mark_read(self, user_id: UUID, ids: Collection[UUID] | None, now: datetime) -> int:
        """Marca como leídas las indicadas (None = todas) del usuario; devuelve cuántas."""
        ...
