import re
from dataclasses import dataclass
from typing import Self

from app.domain.exceptions.errors import InvalidValue

EMAIL_MAX_LENGTH = 254
_EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


@dataclass(frozen=True, slots=True)
class Email:
    """Email normalizado (minúsculas, sin espacios): base de la unicidad."""

    value: str

    def __post_init__(self) -> None:
        if (
            len(self.value) > EMAIL_MAX_LENGTH
            or self.value != self.value.lower()
            or _EMAIL_PATTERN.fullmatch(self.value) is None
        ):
            raise InvalidValue("Email inválido", field="email")

    @classmethod
    def parse(cls, raw: str) -> Self:
        return cls(raw.strip().lower())

    def __str__(self) -> str:
        return self.value
