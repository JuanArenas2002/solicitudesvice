from typing import Protocol
from uuid import UUID

from app.application.dto.page import Page, PageRequest
from app.application.queries.users import UserFilter
from app.domain.entities.user import User
from app.domain.value_objects.email import Email


class UserRepository(Protocol):
    def get(self, user_id: UUID) -> User | None: ...

    def get_by_email(self, email: Email) -> User | None: ...

    def add(self, user: User) -> None:
        """Lanza DuplicateEmail si el email ya existe."""
        ...

    def save(self, user: User) -> None:
        """Persiste cambios de un usuario existente. Lanza DuplicateEmail si choca el email."""
        ...

    def list(self, filters: UserFilter, page: PageRequest) -> Page[User]: ...
