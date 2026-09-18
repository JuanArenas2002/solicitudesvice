import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Self

from app.domain.exceptions.errors import InvalidValue
from app.domain.value_objects.text import clean_optional, clean_required

CODE_PATTERN = r"^[A-Z][A-Z0-9_]{1,29}$"  # sin barras invertidas: igual en Python y PostgreSQL
NAME_MAX = 120
# Nombre de carpeta seguro (sin separadores ni puntos): igual en Python y PostgreSQL.
FOLDER_NAME_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_-]{0,49}$"
DESCRIPTION_MAX = 500


def default_folder_name(name: str) -> str:
    """ "Artículo científico" -> "Articulo_cientifico" (sin tildes ni caracteres especiales)."""
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "_", plain).strip("_")[:50]


@dataclass(eq=False)
class ProductType:
    """Un tipo de producto de investigación (Artículo, Libro, ...). Se crea desde el sistema."""

    code: str
    name: str
    created_at: datetime
    updated_at: datetime
    description: str | None = None
    is_active: bool = True
    id: int | None = None
    folder_name: str = ""  # carpeta de los soportes; se fija al crear y no cambia

    @classmethod
    def create(
        cls,
        code: str,
        name: str,
        description: str | None,
        now: datetime,
        folder_name: str | None = None,
    ) -> Self:
        normalized = code.strip().upper()
        if re.fullmatch(CODE_PATTERN, normalized) is None:
            raise InvalidValue(
                "code debe iniciar con letra y usar solo mayúsculas, dígitos y _ (2 a 30)",
                field="code",
            )
        clean_name = clean_required(name, "name", NAME_MAX)
        folder = (folder_name or default_folder_name(clean_name)).strip()
        if re.fullmatch(FOLDER_NAME_PATTERN, folder) is None:
            raise InvalidValue(
                "folder_name: solo letras, dígitos, _ y - (máx. 50), sin espacios ni puntos",
                field="folder_name",
            )
        return cls(
            code=normalized,
            name=clean_name,
            folder_name=folder,
            description=clean_optional(description, "description", DESCRIPTION_MAX),
            created_at=now,
            updated_at=now,
        )

    def update(
        self,
        now: datetime,
        *,
        name: str | None = None,
        description: str | None = None,
        is_active: bool | None = None,
    ) -> None:
        if name is not None:
            self.name = clean_required(name, "name", NAME_MAX)
        if description is not None:
            self.description = clean_optional(description, "description", DESCRIPTION_MAX)
        if is_active is not None:
            self.is_active = is_active
        self.updated_at = now
