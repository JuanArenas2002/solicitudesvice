from typing import Protocol
from uuid import UUID

from app.domain.entities.status_change import StatusChange


class RequestStatusHistoryRepository(Protocol):
    """Append-only: solo se agrega y se consulta."""

    def add(self, change: StatusChange) -> None: ...

    def list(self, request_id: UUID) -> list[StatusChange]:
        """En orden cronológico."""
        ...
