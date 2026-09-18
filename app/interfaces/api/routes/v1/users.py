from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from app.application.commands.users import (
    CreateUserCommand,
    ResetPasswordCommand,
    SetUserActiveCommand,
    UpdateUserCommand,
)
from app.application.queries.users import UserFilter
from app.domain.enums.role import Role
from app.interfaces.api.dependencies import ActorDep, ContainerDep, ContextDep
from app.interfaces.api.schemas.auth import UserOut
from app.interfaces.api.schemas.common import PageNumber, PageOut, PageSize, page_request
from app.interfaces.api.schemas.users import (
    ResetPasswordIn,
    UserCreateIn,
    UserProductsIn,
    UserUpdateIn,
)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=PageOut[UserOut], summary="Listar usuarios (ADMIN)")
def list_users(
    actor: ActorDep,
    container: ContainerDep,
    page: PageNumber = 1,
    page_size: PageSize = 20,
    role: Role | None = None,
    is_active: bool | None = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> PageOut[UserOut]:
    result = container.list_users().execute(
        actor, UserFilter(role, is_active, search), page_request(page, page_size)
    )
    return PageOut.of(result, [UserOut.of(u) for u in result.items])


@router.get(
    "/product-assignments",
    response_model=dict[UUID, list[int]],
    summary="Productos asignados de cada administrativo (ADMIN)",
)
def product_assignments(actor: ActorDep, container: ContainerDep) -> dict[UUID, list[int]]:
    found = container.list_product_assignments().execute(actor)
    return {user_id: sorted(ids) for user_id, ids in found.items()}


@router.post(
    "", response_model=UserOut, status_code=status.HTTP_201_CREATED, summary="Crear usuario"
)
def create_user(
    body: UserCreateIn, actor: ActorDep, container: ContainerDep, ctx: ContextDep
) -> UserOut:
    user = container.create_user().execute(
        actor,
        CreateUserCommand(body.first_name, body.last_name, body.email, body.role, body.password),
        ctx,
    )
    return UserOut.of(user)


@router.get("/{user_id}", response_model=UserOut, summary="Ver un usuario")
def get_user(user_id: UUID, actor: ActorDep, container: ContainerDep) -> UserOut:
    return UserOut.of(container.get_user().execute(actor, user_id))


@router.patch("/{user_id}", response_model=UserOut, summary="Editar un usuario")
def update_user(
    user_id: UUID, body: UserUpdateIn, actor: ActorDep, container: ContainerDep, ctx: ContextDep
) -> UserOut:
    user = container.update_user().execute(
        actor,
        UpdateUserCommand(user_id, body.first_name, body.last_name, body.email, body.role),
        ctx,
    )
    return UserOut.of(user)


@router.patch("/{user_id}/activate", response_model=UserOut, summary="Activar un usuario")
def activate(user_id: UUID, actor: ActorDep, container: ContainerDep, ctx: ContextDep) -> UserOut:
    user = container.set_user_active().execute(actor, SetUserActiveCommand(user_id, True), ctx)
    return UserOut.of(user)


@router.patch(
    "/{user_id}/deactivate",
    response_model=UserOut,
    summary="Desactivar un usuario (no se elimina; se cierran sus sesiones)",
)
def deactivate(user_id: UUID, actor: ActorDep, container: ContainerDep, ctx: ContextDep) -> UserOut:
    user = container.set_user_active().execute(actor, SetUserActiveCommand(user_id, False), ctx)
    return UserOut.of(user)


@router.post(
    "/{user_id}/reset-password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Asignar una contraseña temporal",
)
def reset_password(
    user_id: UUID,
    body: ResetPasswordIn,
    actor: ActorDep,
    container: ContainerDep,
    ctx: ContextDep,
) -> Response:
    container.reset_password().execute(actor, ResetPasswordCommand(user_id, body.new_password), ctx)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{user_id}/products",
    response_model=UserProductsIn,
    summary="Productos (formularios) que revisa un administrativo",
)
def get_products(user_id: UUID, actor: ActorDep, container: ContainerDep) -> UserProductsIn:
    ids = container.get_user_products().execute(actor, user_id)
    return UserProductsIn(product_type_ids=sorted(ids))


@router.put(
    "/{user_id}/products",
    response_model=UserProductsIn,
    summary="Asignar productos a un administrativo (solo ve y revisa esos)",
)
def set_products(
    user_id: UUID,
    body: UserProductsIn,
    actor: ActorDep,
    container: ContainerDep,
    ctx: ContextDep,
) -> UserProductsIn:
    ids = container.set_user_products().execute(actor, user_id, body.product_type_ids, ctx)
    return UserProductsIn(product_type_ids=sorted(ids))
