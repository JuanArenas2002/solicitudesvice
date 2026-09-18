from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class Journal:
    title: str
    publisher: str | None
    country: str | None
    issn_print: str | None
    eissn: str | None
    open_access: bool | None


class JournalCatalog(Protocol):
    """Catálogo institucional de revistas: valida que un ISSN exista."""

    def find(self, issn: str) -> Journal | None:
        """None si el ISSN no existe. Lanza JournalServiceUnavailable si no se pudo consultar."""
        ...
