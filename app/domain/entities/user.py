from dataclasses import dataclass, field
from datetime import datetime
from typing import Self
from uuid import UUID, uuid4

from app.domain.enums.role import Role
from app.domain.value_objects.email import Email
from app.domain.value_objects.text import clean_required

NAME_MAX = 100


@dataclass(eq=False)
class User:
    """Los usuarios nunca se eliminan: se desactivan (is_active)."""

    first_name: str
    last_name: str
    email: Email
    password_hash: str
    role: Role
    created_at: datetime
    updated_at: datetime
    is_active: bool = True
    last_login_at: datetime | None = None
    id: UUID = field(default_factory=uuid4)

    @classmethod
    def create(
        cls,
        *,
        first_name: str,
        last_name: str,
        email: str,
        password_hash: str,
        role: Role,
        now: datetime,
    ) -> Self:
        return cls(
            first_name=clean_required(first_name, "first_name", NAME_MAX),
            last_name=clean_required(last_name, "last_name", NAME_MAX),
            email=Email.parse(email),
            password_hash=password_hash,
            role=role,
            created_at=now,
            updated_at=now,
        )

    def update_profile(
        self,
        now: datetime,
        *,
        first_name: str | None = None,
        last_name: str | None = None,
        email: str | None = None,
        role: Role | None = None,
    ) -> None:
        if first_name is not None:
            self.first_name = clean_required(first_name, "first_name", NAME_MAX)
        if last_name is not None:
            self.last_name = clean_required(last_name, "last_name", NAME_MAX)
        if email is not None:
            self.email = Email.parse(email)
        if role is not None:
            self.role = role
        self.updated_at = now

    def set_active(self, active: bool, now: datetime) -> None:
        self.is_active = active
        self.updated_at = now

    def set_password_hash(self, password_hash: str, now: datetime) -> None:
        self.password_hash = password_hash
        self.updated_at = now

    def record_login(self, now: datetime) -> None:
        self.last_login_at = now
