from typing import Protocol

from app.application.dto.forms import FormVersionSummary
from app.domain.forms.definition import FormVersion


class FormRepository(Protocol):
    """Las versiones se devuelven completas (secciones, campos y opciones) con sus ids."""

    def get(self, version_id: int, *, for_update: bool = False) -> FormVersion | None:
        """`for_update` bloquea la fila: serializa publicaciones y ediciones concurrentes."""
        ...

    def get_published(
        self, product_type_id: int, *, for_update: bool = False
    ) -> FormVersion | None: ...

    def get_draft(
        self, product_type_id: int, *, for_update: bool = False
    ) -> FormVersion | None: ...

    def list_versions(self, product_type_id: int) -> list[FormVersionSummary]: ...

    def next_version_number(self, product_type_id: int) -> int: ...

    def add(self, version: FormVersion) -> FormVersion:
        """Lanza FormDraftExists si ya hay un borrador (o el número de versión choca)."""
        ...

    def save(self, version: FormVersion) -> FormVersion:
        """Persiste estado y fechas; la estructura solo se reemplaza si es un borrador."""
        ...
