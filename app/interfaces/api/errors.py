"""Traducción de errores de dominio a respuestas HTTP (sin detalles internos ni datos sensibles)."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config.logging import correlation_id_var
from app.domain.exceptions import errors as e

log = logging.getLogger("app.errors")

# Del más específico al más general: se toma el primer tipo del que la excepción sea instancia.
STATUS_BY_ERROR: tuple[tuple[type[e.DomainError], int], ...] = (
    (e.FileTooLarge, 413),
    (e.JournalServiceUnavailable, 503),
    (e.JournalNotFound, 404),
    (e.InvalidValue, 422),
    (e.IncompleteProduct, 422),
    (e.Unauthorized, 401),
    (e.Forbidden, 403),
    (e.RequestNotFound, 404),
    (e.UserNotFound, 404),
    (e.ProductTypeNotFound, 404),
    (e.FormVersionNotFound, 404),
    (e.InvalidStatusTransition, 409),
    (e.InvalidRequestState, 409),
    (e.ConcurrentModification, 409),
    (e.DuplicateEmail, 409),
    (e.DuplicateProductType, 409),
    (e.FormNotEditable, 409),
    (e.FormDraftExists, 409),
    (e.AttachmentNotFound, 404),
    (e.DuplicateAttachment, 409),
    (e.AttachmentLimitReached, 409),
    (e.CedulaLocked, 409),
    (e.DomainError, 400),
)


def status_for(error: e.DomainError) -> int:
    return next(code for kind, code in STATUS_BY_ERROR if isinstance(error, kind))


def problem(status: int, detail: str, **extra: object) -> JSONResponse:
    body: dict[str, object] = {"detail": detail, "correlation_id": correlation_id_var.get()}
    body.update({k: v for k, v in extra.items() if v is not None})
    headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None
    return JSONResponse(body, status_code=status, headers=headers)


def domain_problem(error: e.DomainError) -> JSONResponse:
    return problem(
        status_for(error),
        error.message,
        code=type(error).__name__,
        field=getattr(error, "field", None),
        missing=list(error.missing) if isinstance(error, e.IncompleteProduct) else None,
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(e.DomainError)
    async def _domain(request: Request, error: e.DomainError) -> JSONResponse:
        return domain_problem(error)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, error: RequestValidationError) -> JSONResponse:
        # Se descartan `input` y `ctx`: podrían devolver al cliente contraseñas u otros datos.
        errors = [
            {"loc": [str(p) for p in item["loc"]], "message": item["msg"]}
            for item in error.errors()
        ]
        return problem(422, "Datos de entrada inválidos", code="ValidationError", errors=errors)

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, error: Exception) -> JSONResponse:
        log.exception("Error no controlado", extra={"path": request.url.path})
        return problem(500, "Error interno del servidor")  # sin stack ni detalles
