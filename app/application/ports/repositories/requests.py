from typing import Protocol
from uuid import UUID

from app.application.dto.page import Page, PageRequest
from app.application.dto.requests import RequestSummary
from app.application.queries.requests import RequestFilter
from app.domain.entities.research_product_request import ResearchProductRequest
from app.domain.services.access_policy import RequestScope


class ResearchProductRequestRepository(Protocol):
    def add(self, request: ResearchProductRequest) -> None: ...

    def get(self, request_id: UUID, *, for_update: bool = False) -> ResearchProductRequest | None:
        """Carga el agregado con sus correcciones. `for_update` bloquea la fila."""
        ...

    def save(self, request: ResearchProductRequest) -> None:
        """Persiste estado, fechas y correcciones (ConcurrentModification si la versión cambió)."""
        ...

    def search(
        self, scope: RequestScope, filters: RequestFilter, page: PageRequest
    ) -> Page[RequestSummary]:
        """El `scope` (qué puede ver el actor) se aplica siempre dentro de la consulta."""
        ...
