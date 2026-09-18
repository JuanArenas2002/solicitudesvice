from dataclasses import dataclass, field
from uuid import UUID

from app.domain.enums.role import Role


@dataclass(frozen=True, slots=True)
class CreateUserCommand:
    first_name: str
    last_name: str
    email: str
    role: Role
    password: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class UpdateUserCommand:
    """Solo los campos distintos de None se modifican."""

    user_id: UUID
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    role: Role | None = None


@dataclass(frozen=True, slots=True)
class SetUserActiveCommand:
    user_id: UUID
    active: bool


@dataclass(frozen=True, slots=True)
class ResetPasswordCommand:
    user_id: UUID
    new_password: str = field(repr=False)
