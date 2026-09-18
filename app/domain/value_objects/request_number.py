import re
from dataclasses import dataclass
from typing import Self

from app.domain.exceptions.errors import InvalidValue

REQUEST_NUMBER_PATTERN = r"^SOL-[0-9]{4}-[0-9]{6}$"
MAX_SEQUENCE = 999_999
_PARSE = re.compile(r"SOL-([0-9]{4})-([0-9]{6})")


@dataclass(frozen=True, slots=True)
class RequestNumber:
    """Número legible SOL-AAAA-NNNNNN. La secuencia la asigna un contador transaccional por año."""

    year: int
    sequence: int

    def __post_init__(self) -> None:
        if not 1000 <= self.year <= 9999:
            raise InvalidValue("Año de solicitud inválido", field="request_number")
        if not 1 <= self.sequence <= MAX_SEQUENCE:
            raise InvalidValue("Secuencia de solicitud fuera de rango", field="request_number")

    @classmethod
    def parse(cls, raw: str) -> Self:
        match = _PARSE.fullmatch(raw.strip().upper())
        if match is None:
            raise InvalidValue("Número de solicitud inválido", field="request_number")
        return cls(int(match.group(1)), int(match.group(2)))

    def __str__(self) -> str:
        return f"SOL-{self.year:04d}-{self.sequence:06d}"
