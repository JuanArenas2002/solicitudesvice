import re
from dataclasses import dataclass
from typing import Self

from app.domain.exceptions.errors import InvalidValue

# Sin barras invertidas: Python `re` y PostgreSQL los interpretan igual (los CHECK los reutilizan).
DOI_PATTERN = r"^10[.][0-9]{4,9}/[^ ]+$"
ISSN_PATTERN = r"^[0-9]{4}-[0-9]{3}[0-9X]$"
URL_PATTERN = r"^https?://[^ ]+$"
URL_MAX_LENGTH = 2048
CEDULA_PATTERN = r"^[0-9]{5,15}$"
DOI_MAX_LENGTH = 255


def _validate(value: str, pattern: str, field: str) -> None:
    if re.fullmatch(pattern, value) is None:
        raise InvalidValue(f"{field} con formato inválido", field=field)


@dataclass(frozen=True, slots=True)
class Doi:
    value: str

    def __post_init__(self) -> None:
        if len(self.value) > DOI_MAX_LENGTH:
            raise InvalidValue("doi excede la longitud máxima", field="doi")
        _validate(self.value, DOI_PATTERN, "doi")

    @classmethod
    def parse(cls, raw: str) -> Self:
        return cls(raw.strip())

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class Issn:
    """Sirve para ISSN y eISSN."""

    value: str

    def __post_init__(self) -> None:
        _validate(self.value, ISSN_PATTERN, "issn")

    @classmethod
    def parse(cls, raw: str, field: str = "issn") -> Self:
        """Acepta "0378-595X" y también "0378595X" (el guion es opcional); se guarda con guion."""
        value = raw.strip().upper().replace(" ", "")
        if re.fullmatch(r"^[0-9]{7}[0-9X]$", value):
            value = f"{value[:4]}-{value[4:]}"
        _validate(value, ISSN_PATTERN, field)
        return cls(value)

    def __str__(self) -> str:
        return self.value
