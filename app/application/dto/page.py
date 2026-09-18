from dataclasses import dataclass

from app.domain.exceptions.errors import InvalidValue

MAX_PAGE_SIZE = 100


@dataclass(frozen=True, slots=True)
class PageRequest:
    """Paginación por offset con tope de tamaño: ninguna consulta puede traer toda la tabla."""

    page: int = 1
    page_size: int = 20

    def __post_init__(self) -> None:
        if self.page < 1:
            raise InvalidValue("page debe ser mayor o igual a 1", field="page")
        if not 1 <= self.page_size <= MAX_PAGE_SIZE:
            raise InvalidValue(f"page_size debe estar entre 1 y {MAX_PAGE_SIZE}", field="page_size")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


@dataclass(frozen=True, slots=True)
class Page[T]:
    items: tuple[T, ...]
    total: int
    page: int
    page_size: int

    @property
    def total_pages(self) -> int:
        return -(-self.total // self.page_size)  # división hacia arriba
