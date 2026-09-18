from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.entities.user import User
from app.domain.enums.role import Role
from app.domain.services.authorizer import ROLE_PERMISSIONS
from app.interfaces.api.schemas.common import Input


class LoginIn(Input):
    email: str = Field(max_length=254)
    password: str = Field(max_length=128, repr=False)


class ChangePasswordIn(Input):
    current_password: str = Field(max_length=128, repr=False)
    new_password: str = Field(max_length=128, repr=False)


class UserOut(BaseModel):
    """Nunca incluye contraseña, hash ni tokens."""

    id: UUID
    first_name: str
    last_name: str
    email: str
    role: Role
    is_active: bool
    permissions: list[str] = Field(description="Permisos del rol (solo para adaptar la interfaz)")
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None

    @classmethod
    def of(cls, user: User) -> "UserOut":
        return cls(
            id=user.id,
            first_name=user.first_name,
            last_name=user.last_name,
            email=user.email.value,
            role=user.role,
            is_active=user.is_active,
            permissions=sorted(ROLE_PERMISSIONS[user.role]),
            created_at=user.created_at,
            updated_at=user.updated_at,
            last_login_at=user.last_login_at,
        )


class TokenOut(BaseModel):
    """El refresh token viaja únicamente en una cookie HttpOnly, jamás en el cuerpo."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int


class LoginOut(TokenOut):
    user: UserOut
