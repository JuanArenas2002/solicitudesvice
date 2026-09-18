from pydantic import Field

from app.domain.enums.role import Role
from app.interfaces.api.schemas.common import Input


class UserCreateIn(Input):
    first_name: str = Field(max_length=100)
    last_name: str = Field(max_length=100)
    email: str = Field(max_length=254)
    role: Role
    password: str = Field(max_length=128, repr=False)


class UserUpdateIn(Input):
    """Solo los campos enviados se modifican."""

    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    email: str | None = Field(default=None, max_length=254)
    role: Role | None = None


class UserProductsIn(Input):
    product_type_ids: list[int] = Field(max_length=200)


class ResetPasswordIn(Input):
    new_password: str = Field(max_length=128, repr=False)
