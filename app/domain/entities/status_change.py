from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.domain.enums.request_status import RequestStatus


@dataclass(frozen=True, slots=True)
class StatusChange:
    """Registro inmutable del historial de estados (previous_status es None al crear)."""

    request_id: UUID
    previous_status: RequestStatus | None
    new_status: RequestStatus
    changed_by: UUID
    occurred_at: datetime
    reason: str | None = None
