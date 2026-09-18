import ipaddress
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.application.commands.context import RequestContext
from app.config.logging import correlation_id_var, user_id_var
from app.domain.exceptions.errors import Unauthorized
from app.domain.value_objects.actor import Actor
from app.interfaces.api.container import Container

_bearer = HTTPBearer(auto_error=False, description="Access token (JWT) de /auth/login")


def get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


def _valid_ip(host: str | None) -> str | None:
    """La bitácora guarda `inet`: cualquier valor que no sea una IP (socket unix, test) se omite."""
    try:
        return str(ipaddress.ip_address(host)) if host else None
    except ValueError:
        return None


def get_context(request: Request) -> RequestContext:
    client = request.client
    return RequestContext(
        correlation_id=correlation_id_var.get(),
        ip_address=_valid_ip(client.host if client else None),
    )


def get_actor(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    container: Annotated[Container, Depends(get_container)],
) -> Actor:
    """Autentica en CADA petición protegida: firma, sesión viva y usuario activo (de la BD)."""
    if credentials is None:
        raise Unauthorized("Falta el token de acceso")
    actor = container.authenticate().execute(credentials.credentials)
    user_id_var.set(str(actor.user_id))
    return actor


ContainerDep = Annotated[Container, Depends(get_container)]
ContextDep = Annotated[RequestContext, Depends(get_context)]
ActorDep = Annotated[Actor, Depends(get_actor)]
