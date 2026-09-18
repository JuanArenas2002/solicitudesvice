from typing import Protocol

from app.domain.value_objects.request_number import RequestNumber


class RequestNumberGenerator(Protocol):
    def next(self, year: int) -> RequestNumber:
        """Siguiente SOL-AAAA-NNNNNN. Seguro ante concurrencia; se confirma con la transacción."""
        ...
