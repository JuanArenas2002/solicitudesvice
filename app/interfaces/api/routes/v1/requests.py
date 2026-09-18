from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.application.queries.requests import RequestFilter
from app.domain.enums.request_status import RequestStatus
from app.interfaces.api.dependencies import ActorDep, ContainerDep, ContextDep
from app.interfaces.api.schemas.common import PageNumber, PageOut, PageSize, page_request
from app.interfaces.api.schemas.requests import (
    AnswersUpdateIn,
    ChangeStatusIn,
    CorrectionIn,
    CorrectionOut,
    CreateRequestIn,
    HistoryEntryOut,
    ReasonIn,
    RequestDetailOut,
    RequestSummaryOut,
    RequiredReasonIn,
)

router = APIRouter(prefix="/requests", tags=["requests"])


@router.get(
    "",
    response_model=PageOut[RequestSummaryOut],
    summary="Listar solicitudes (el mentor ve las suyas; el personal, las enviadas)",
)
def list_requests(
    actor: ActorDep,
    container: ContainerDep,
    page: PageNumber = 1,
    page_size: PageSize = 20,
    status_: Annotated[RequestStatus | None, Query(alias="status")] = None,
    product_type_id: int | None = None,
    mentor_id: UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    request_number: Annotated[str | None, Query(max_length=15)] = None,
) -> PageOut[RequestSummaryOut]:
    filters = RequestFilter(status_, product_type_id, mentor_id, date_from, date_to, request_number)
    result = container.list_requests().execute(actor, filters, page_request(page, page_size))
    return PageOut.of(result, [RequestSummaryOut.of(s) for s in result.items])


@router.post(
    "",
    response_model=RequestDetailOut,
    status_code=status.HTTP_201_CREATED,
    summary="Iniciar una solicitud (borrador) para un producto",
)
def create_request(
    body: CreateRequestIn, actor: ActorDep, container: ContainerDep, ctx: ContextDep
) -> RequestDetailOut:
    return RequestDetailOut.of(container.create_request().execute(actor, body.product_type_id, ctx))


@router.get("/{request_id}", response_model=RequestDetailOut, summary="Detalle de una solicitud")
def get_request(request_id: UUID, actor: ActorDep, container: ContainerDep) -> RequestDetailOut:
    return RequestDetailOut.of(container.get_request().execute(actor, request_id))


@router.patch(
    "/{request_id}/answers",
    response_model=RequestDetailOut,
    summary="Guardar respuestas parciales (solo el dueño, en borrador o corrección)",
)
def update_answers(
    request_id: UUID,
    body: AnswersUpdateIn,
    actor: ActorDep,
    container: ContainerDep,
    ctx: ContextDep,
) -> RequestDetailOut:
    detail = container.update_answers().execute(actor, request_id, body.answers, body.version, ctx)
    return RequestDetailOut.of(detail)


# ---------------- transiciones: el estado nunca lo envía el cliente ----------------
@router.post("/{request_id}/submit", response_model=RequestDetailOut, summary="Enviar")
def submit(
    request_id: UUID, actor: ActorDep, container: ContainerDep, ctx: ContextDep
) -> RequestDetailOut:
    return RequestDetailOut.of(container.submit_request().execute(actor, request_id, ctx))


@router.post("/{request_id}/review", response_model=RequestDetailOut, summary="Tomar en revisión")
def review(
    request_id: UUID, actor: ActorDep, container: ContainerDep, ctx: ContextDep
) -> RequestDetailOut:
    return RequestDetailOut.of(container.start_review().execute(actor, request_id, ctx))


@router.post(
    "/{request_id}/request-correction",
    response_model=RequestDetailOut,
    summary="Solicitar una corrección al mentor",
)
def request_correction(
    request_id: UUID,
    body: CorrectionIn,
    actor: ActorDep,
    container: ContainerDep,
    ctx: ContextDep,
) -> RequestDetailOut:
    detail = container.request_correction().execute(actor, request_id, body.description, ctx)
    return RequestDetailOut.of(detail)


@router.post(
    "/{request_id}/resubmit", response_model=RequestDetailOut, summary="Reenviar corregida"
)
def resubmit(
    request_id: UUID, actor: ActorDep, container: ContainerDep, ctx: ContextDep
) -> RequestDetailOut:
    return RequestDetailOut.of(container.resubmit_request().execute(actor, request_id, ctx))


@router.post("/{request_id}/approve", response_model=RequestDetailOut, summary="Aprobar")
def approve(
    request_id: UUID,
    body: ReasonIn,
    actor: ActorDep,
    container: ContainerDep,
    ctx: ContextDep,
) -> RequestDetailOut:
    detail = container.approve_request().execute(actor, request_id, body.reason, ctx)
    return RequestDetailOut.of(detail)


@router.post("/{request_id}/reject", response_model=RequestDetailOut, summary="Rechazar")
def reject(
    request_id: UUID,
    body: RequiredReasonIn,
    actor: ActorDep,
    container: ContainerDep,
    ctx: ContextDep,
) -> RequestDetailOut:
    detail = container.reject_request().execute(actor, request_id, body.reason, ctx)
    return RequestDetailOut.of(detail)


@router.post(
    "/{request_id}/change-status",
    response_model=RequestDetailOut,
    summary="Cambiar el estado a cualquiera (personal administrativo, con motivo)",
)
def change_status(
    request_id: UUID,
    body: ChangeStatusIn,
    actor: ActorDep,
    container: ContainerDep,
    ctx: ContextDep,
) -> RequestDetailOut:
    detail = container.change_request_status().execute(
        actor, request_id, body.status, body.reason, ctx
    )
    return RequestDetailOut.of(detail)


@router.get(
    "/{request_id}/history",
    response_model=list[HistoryEntryOut],
    summary="Historial de estados",
)
def history(request_id: UUID, actor: ActorDep, container: ContainerDep) -> list[HistoryEntryOut]:
    return [HistoryEntryOut.of(h) for h in container.request_history().execute(actor, request_id)]


@router.get(
    "/{request_id}/corrections",
    response_model=list[CorrectionOut],
    summary="Correcciones solicitadas (abiertas y resueltas)",
)
def corrections(request_id: UUID, actor: ActorDep, container: ContainerDep) -> list[CorrectionOut]:
    return [CorrectionOut.of(c) for c in container.list_corrections().execute(actor, request_id)]
