from typing import Protocol

from app.application.dto.page import Page, PageRequest
from app.domain.entities.product_type import ProductType


class ProductTypeRepository(Protocol):
    def get(self, product_type_id: int) -> ProductType | None: ...

    def get_by_code(self, code: str) -> ProductType | None: ...

    def add(self, product_type: ProductType) -> None:
        """Asigna el id. Lanza DuplicateProductType si el código ya existe."""
        ...

    def save(self, product_type: ProductType) -> None: ...

    def list(self, only_active: bool, page: PageRequest) -> Page[ProductType]: ...
