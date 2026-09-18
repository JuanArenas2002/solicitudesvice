from dataclasses import dataclass
from datetime import date
from uuid import UUID

from app.domain.enums.request_status import RequestStatus


@dataclass(frozen=True, slots=True)
class RequestFilter:
    status: RequestStatus | None = None
    product_type_id: int | None = None
    mentor_id: UUID | None = None  # solo tiene efecto para quien ve solicitudes de varios mentores
    date_from: date | None = None  # sobre created_at, inclusive
    date_to: date | None = None
    request_number: str | None = None  # prefijo, p. ej. SOL-2026
