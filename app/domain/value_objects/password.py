from dataclasses import dataclass, field

from app.domain.exceptions.errors import PasswordPolicyViolation

PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_LENGTH = 128  # tope para no dar a Argon2 entradas arbitrariamente costosas


@dataclass(frozen=True, slots=True)
class PlainPassword:
    """Contraseña en claro validada. Nunca se imprime (repr oculto) ni se persiste."""

    value: str = field(repr=False)

    def __post_init__(self) -> None:
        if not PASSWORD_MIN_LENGTH <= len(self.value) <= PASSWORD_MAX_LENGTH:
            raise PasswordPolicyViolation(
                f"La contraseña debe tener entre {PASSWORD_MIN_LENGTH} y "
                f"{PASSWORD_MAX_LENGTH} caracteres",
                field="password",
            )
