from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from app.domain.enums.request_status import RequestStatus


@dataclass(frozen=True, slots=True)
class Notification:
    """Aviso para un usuario: su solicitud cambió de estado por una acción de otra persona."""

    user_id: UUID
    request_id: UUID
    request_number: str
    status: RequestStatus  # el estado al que pasó
    created_at: datetime
    reason: str | None = None
    read_at: datetime | None = None
    id: UUID = field(default_factory=uuid4)

    @property
    def is_read(self) -> bool:
        return self.read_at is not None
