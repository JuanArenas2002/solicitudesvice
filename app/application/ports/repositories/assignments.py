from collections.abc import Collection
from typing import Protocol
from uuid import UUID


class ProductAssignmentRepository(Protocol):
    """Qué productos revisa cada usuario administrativo."""

    def product_ids(self, user_id: UUID) -> frozenset[int]: ...

    def all(self) -> dict[UUID, frozenset[int]]:
        """Productos asignados de cada usuario que tiene alguno."""
        ...

    def replace(self, user_id: UUID, product_ids: Collection[int]) -> None:
        """Deja asignados exactamente estos productos (los anteriores se descartan)."""
        ...
