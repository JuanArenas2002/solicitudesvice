from typing import Annotated

from fastapi import Query
from pydantic import BaseModel, ConfigDict

from app.application.dto.page import MAX_PAGE_SIZE, Page, PageRequest


class Input(BaseModel):
    """Base de las entradas: rechaza campos desconocidos y no repite los datos en los errores."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class PageOut[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int

    @classmethod
    def of[S](cls, page: Page[S], items: list[T]) -> "PageOut[T]":
        return cls(
            items=items,
            total=page.total,
            page=page.page,
            page_size=page.page_size,
            total_pages=page.total_pages,
        )


PageNumber = Annotated[int, Query(ge=1, description="Página (desde 1)")]
PageSize = Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE, description="Tamaño de página (máx. 100)")]


def page_request(page: int, page_size: int) -> PageRequest:
    return PageRequest(page, page_size)
