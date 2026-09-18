from typing import Annotated

from fastapi import APIRouter, Cookie, Header, Request, Response, status
from fastapi.responses import JSONResponse

from app.application.commands.auth import ChangePasswordCommand, LoginCommand, RefreshCommand
from app.application.dto.auth import SessionTokens
from app.domain.exceptions.errors import Forbidden, Unauthorized
from app.interfaces.api.dependencies import ActorDep, ContainerDep, ContextDep
from app.interfaces.api.errors import domain_problem
from app.interfaces.api.schemas.auth import ChangePasswordIn, LoginIn, LoginOut, TokenOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "refresh_token"
CSRF_COOKIE = "csrf_token"
COOKIE_PATH = "/api/v1/auth"  # la cookie de refresh solo viaja hacia estos endpoints


def _set_cookies(response: Response, container: ContainerDep, tokens: SessionTokens) -> None:
    """Refresh token en cookie HttpOnly; CSRF en cookie legible por el SPA (doble envío)."""
    settings = container.settings
    max_age = int((tokens.refresh_expires_at - container.clock.now()).total_seconds())
    response.set_cookie(
        REFRESH_COOKIE,
        tokens.refresh_token,
        max_age=max_age,
        path=COOKIE_PATH,
        domain=settings.cookie_domain,
        secure=settings.cookie_secure,
        httponly=True,
        samesite=settings.cookie_samesite,
    )
    response.set_cookie(
        CSRF_COOKIE,
        container.csrf.issue(tokens.refresh_token),
        max_age=max_age,
        path="/",
        domain=settings.cookie_domain,
        secure=settings.cookie_secure,
        httponly=False,  # el SPA debe poder leerla para enviarla en X-CSRF-Token
        samesite=settings.cookie_samesite,
    )


def _clear_cookies(response: Response, container: ContainerDep) -> None:
    domain = container.settings.cookie_domain
    response.delete_cookie(REFRESH_COOKIE, path=COOKIE_PATH, domain=domain)
    response.delete_cookie(CSRF_COOKIE, path="/", domain=domain)


def _token_out(container: ContainerDep, tokens: SessionTokens) -> TokenOut:
    expires_in = int((tokens.access_expires_at - container.clock.now()).total_seconds())
    return TokenOut(access_token=tokens.access_token, expires_in=max(expires_in, 0))


@router.post("/login", response_model=LoginOut, summary="Iniciar sesión")
def login(body: LoginIn, response: Response, container: ContainerDep, ctx: ContextDep) -> LoginOut:
    result = container.login().execute(LoginCommand(body.email, body.password), ctx)
    _set_cookies(response, container, result.tokens)
    token = _token_out(container, result.tokens)
    return LoginOut(**token.model_dump(), user=UserOut.of(result.user))


@router.post("/refresh", response_model=TokenOut, summary="Renovar el access token")
def refresh(
    request: Request,
    response: Response,
    container: ContainerDep,
    ctx: ContextDep,
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
    csrf_header: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> TokenOut | JSONResponse:
    """Depende de la cookie, así que exige CSRF: cabecera X-CSRF-Token + Origin permitido."""
    _check_origin(request, container)
    if not refresh_token:
        raise Unauthorized("Sesión inválida")
    if not csrf_header or not container.csrf.verify(refresh_token, csrf_header):
        raise Forbidden("Token CSRF inválido o ausente")
    try:
        tokens = container.refresh_session().execute(RefreshCommand(refresh_token), ctx)
    except Unauthorized as error:  # sesión terminada: se limpian también las cookies
        failure = domain_problem(error)
        _clear_cookies(failure, container)
        return failure
    _set_cookies(response, container, tokens)
    return _token_out(container, tokens)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Cerrar sesión")
def logout(actor: ActorDep, container: ContainerDep, ctx: ContextDep) -> Response:
    container.logout().execute(actor, ctx)
    empty = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_cookies(empty, container)
    return empty


@router.get("/me", response_model=UserOut, summary="Usuario autenticado")
def me(actor: ActorDep, container: ContainerDep) -> UserOut:
    return UserOut.of(container.get_me().execute(actor))


@router.post(
    "/change-password", status_code=status.HTTP_204_NO_CONTENT, summary="Cambiar mi contraseña"
)
def change_password(
    body: ChangePasswordIn, actor: ActorDep, container: ContainerDep, ctx: ContextDep
) -> Response:
    container.change_password().execute(
        actor, ChangePasswordCommand(body.current_password, body.new_password), ctx
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _check_origin(request: Request, container: ContainerDep) -> None:
    """Un navegador siempre envía Origin en POST cross-site: debe ser uno de los permitidos."""
    origin = request.headers.get("origin")
    own = f"{request.url.scheme}://{request.url.netloc}"
    if origin and origin != own and origin not in container.settings.cors_origins:
        raise Forbidden("Origen no permitido")
