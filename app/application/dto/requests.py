from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.domain.entities.product_type import ProductType
from app.domain.entities.research_product_request import ResearchProductRequest
from app.domain.enums.request_status import RequestStatus
from app.domain.forms.filled_form import FilledForm


@dataclass(frozen=True, slots=True)
class RequestSummary:
    """Fila de un listado: se arma con un solo JOIN (sin consultas por cada solicitud)."""

    id: UUID
    request_number: str
    mentor_id: UUID
    mentor_name: str
    product_type_id: int
    product_type_code: str
    product_type_name: str
    form_version_id: int
    status: RequestStatus
    version: int
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None
    reviewed_at: datetime | None


@dataclass(frozen=True, slots=True)
class RequestDetail:
    request: ResearchProductRequest
    mentor_name: str
    product_type: ProductType
    filled: FilledForm  # contiene la versión del formulario y las respuestas
