from dataclasses import dataclass
from uuid import UUID

from app.domain.enums.role import Role


@dataclass(frozen=True, slots=True)
class Actor:
    """Quién ejecuta una acción. Los casos de uso reciben esto, nunca objetos de FastAPI."""

    user_id: UUID
    role: Role
    session_id: UUID | None = None
    # Productos que puede gestionar. None = todos; un administrativo solo ve/revisa los asignados.
    product_scope: frozenset[int] | None = None
