from typing import Protocol
from uuid import UUID


class ProductDetail(Protocol):
    """Contrato que cumple el detalle de cada tipo de producto (artículo, libro, ...).

    El núcleo de solicitudes/workflow solo conoce esto: agregar un producto no lo modifica.
    """

    @property
    def request_id(self) -> UUID: ...

    def missing_for_submission(self) -> tuple[str, ...]:
        """Nombres de los campos que faltan para poder enviar (vacío = completo)."""
        ...
