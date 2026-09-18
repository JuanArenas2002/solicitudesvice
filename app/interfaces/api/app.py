import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from app.config.logging import configure_logging, correlation_id_var, user_id_var
from app.config.settings import Settings, get_settings
from app.interfaces.api.container import Container
from app.interfaces.api.errors import install_error_handlers
from app.interfaces.api.routes.v1 import (
    attachments,
    auth,
    forms,
    health,
    journals,
    notifications,
    requests,
    users,
)

API_PREFIX = "/api/v1"
log = logging.getLogger("app.access")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging()
    production = settings.environment == "production"

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.container = Container(settings)
        yield
        app.state.container.close()

    app = FastAPI(
        title="Solicitudes de productos de investigación",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None if production else "/docs",  # sin documentación pública en producción
        redoc_url=None,
        openapi_url=None if production else "/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,  # necesario para la cookie del refresh token
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next: object) -> Response:
        # Un id de correlación por petición: viaja en logs, auditoría y errores.
        supplied = request.headers.get("X-Request-ID", "")
        correlation_id = (
            supplied if 8 <= len(supplied) <= 64 and supplied.isprintable() else uuid.uuid4().hex
        )
        correlation_id_var.set(correlation_id)
        user_id_var.set(None)
        started = time.perf_counter()
        response: Response = await call_next(request)  # type: ignore[operator]
        route = request.scope.get("route")
        response.headers["X-Request-ID"] = correlation_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        if request.url.path.startswith(f"{API_PREFIX}/auth"):
            response.headers["Cache-Control"] = "no-store"
        log.info(
            "request",
            extra={
                "method": request.method,
                "path": route.path if isinstance(route, APIRoute) else "(sin ruta)",
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            },
        )
        return response

    install_error_handlers(app)
    for router in (
        health.router,
        auth.router,
        users.router,
        forms.router,
        requests.router,
        attachments.router,
        journals.router,
        notifications.router,
    ):
        app.include_router(router, prefix=API_PREFIX)
    return app
