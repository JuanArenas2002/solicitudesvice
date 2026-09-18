from dataclasses import replace
from uuid import UUID

from app.application.dto.page import Page, PageRequest
from app.application.dto.requests import RequestDetail, RequestSummary
from app.application.ports.repositories.unit_of_work import UnitOfWork, UnitOfWorkFactory
from app.application.queries.requests import RequestFilter
from app.domain.entities.request_correction import RequestCorrection
from app.domain.entities.research_product_request import ResearchProductRequest
from app.domain.entities.status_change import StatusChange
from app.domain.exceptions.errors import (
    FormVersionNotFound,
    ProductTypeNotFound,
    RequestNotFound,
    UserNotFound,
)
from app.domain.forms.definition import FormVersion
from app.domain.forms.filled_form import FilledForm
from app.domain.services.access_policy import ensure_can_view, ensure_can_view_history, scope_for
from app.domain.value_objects.actor import Actor


def load_request(
    uow: UnitOfWork, request_id: UUID, *, for_update: bool = False
) -> ResearchProductRequest:
    request = uow.requests.get(request_id, for_update=for_update)
    if request is None:
        raise RequestNotFound("Solicitud no encontrada")
    return request


def load_filled(uow: UnitOfWork, request: ResearchProductRequest, form: FormVersion) -> FilledForm:
    """Respuestas + qué campos de soporte ya tienen archivos (cuentan como "respondidos")."""
    filled = uow.answers.load(request.id, form)
    with_files = {a.field_id for a in uow.attachments.list(request.id)}
    return filled.with_attachments(frozenset(f.key for f in form.fields() if f.id in with_files))


def build_detail(uow: UnitOfWork, request: ResearchProductRequest) -> RequestDetail:
    """Arma el detalle con consultas fijas (sin N+1): formulario, respuestas, producto y mentor."""
    form = uow.forms.get(request.form_version_id)
    if form is None:  # pragma: no cover - el FK lo impide
        raise FormVersionNotFound("Formulario de la solicitud no encontrado")
    product_type = uow.product_types.get(form.product_type_id)
    if product_type is None:  # pragma: no cover - el FK lo impide
        raise ProductTypeNotFound("Producto de la solicitud no encontrado")
    mentor = uow.users.get(request.mentor_id)
    if mentor is None:  # pragma: no cover - el FK lo impide
        raise UserNotFound("Mentor de la solicitud no encontrado")
    return RequestDetail(
        request=request,
        mentor_name=f"{mentor.first_name} {mentor.last_name}",
        product_type=product_type,
        filled=load_filled(uow, request, form),
    )


class GetRequest:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, actor: Actor, request_id: UUID) -> RequestDetail:
        with self._uow_factory() as uow:
            request = load_request(uow, request_id)
            ensure_can_view(actor, request)  # ownership: RequestNotFound si es ajena (IDOR)
            return build_detail(uow, request)


class ListRequests:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(
        self, actor: Actor, filters: RequestFilter, page: PageRequest
    ) -> Page[RequestSummary]:
        scope = scope_for(actor)  # Forbidden si el rol no puede ver solicitudes
        if scope.mentor_id is not None:  # un mentor solo ve las suyas, pida lo que pida
            filters = replace(filters, mentor_id=None)
        with self._uow_factory() as uow:
            return uow.requests.search(scope, filters, page)


class GetRequestHistory:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, actor: Actor, request_id: UUID) -> list[StatusChange]:
        with self._uow_factory() as uow:
            request = load_request(uow, request_id)
            ensure_can_view_history(actor, request)
            return uow.history.list(request_id)


class ListCorrections:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, actor: Actor, request_id: UUID) -> list[RequestCorrection]:
        with self._uow_factory() as uow:
            request = load_request(uow, request_id)
            ensure_can_view(actor, request)
            return list(request.corrections)
