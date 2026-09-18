from dataclasses import dataclass

from app.domain.enums.role import Role


@dataclass(frozen=True, slots=True)
class UserFilter:
    role: Role | None = None
    is_active: bool | None = None
    search: str | None = None  # nombre, apellido o email (contiene, sin distinguir mayúsculas)
