from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.forms.definition import SectionInput


@dataclass(frozen=True, slots=True)
class CreateProductTypeCommand:
    code: str
    name: str
    description: str | None = None
    folder_name: str | None = (
        None  # carpeta de soportes (p. ej. Articulos); por defecto, del nombre
    )


@dataclass(frozen=True, slots=True)
class UpdateProductTypeCommand:
    """Solo los campos distintos de None se modifican."""

    product_type_id: int
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None


@dataclass(frozen=True, slots=True)
class ReplaceFormDraftCommand:
    """Documento completo del borrador (secciones -> campos -> opciones), tal como lo edita el
    constructor de formularios. Reemplaza la estructura anterior del borrador."""

    version_id: int
    sections: Sequence[SectionInput]
