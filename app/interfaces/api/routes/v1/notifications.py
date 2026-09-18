from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field

from app.domain.entities.notification import Notification
from app.domain.enums.request_status import RequestStatus
from app.interfaces.api.dependencies import ActorDep, ContainerDep
from app.interfaces.api.schemas.common import Input, PageNumber, PageOut, PageSize, page_request

router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotificationOut(BaseModel):
    id: UUID
    request_id: UUID
    request_number: str
    status: RequestStatus = Field(description="Estado al que pasó la solicitud")
    reason: str | None
    created_at: datetime
    read_at: datetime | None

    @classmethod
    def of(cls, n: Notification) -> "NotificationOut":
        return cls(
            id=n.id,
            request_id=n.request_id,
            request_number=n.request_number,
            status=n.status,
            reason=n.reason,
            created_at=n.created_at,
            read_at=n.read_at,
        )


class NotificationsOut(PageOut[NotificationOut]):
    unread: int


class UnreadOut(BaseModel):
    unread: int


class MarkReadIn(Input):
    ids: Annotated[list[UUID] | None, Field(max_length=200)] = None  # None = todas


@router.get("", response_model=NotificationsOut, summary="Mis notificaciones")
def list_notifications(
    actor: ActorDep,
    container: ContainerDep,
    page: PageNumber = 1,
    page_size: PageSize = 20,
    unread_only: bool = False,
) -> NotificationsOut:
    result = container.list_notifications().execute(
        actor, unread_only, page_request(page, page_size)
    )
    base = PageOut.of(result.page, [NotificationOut.of(n) for n in result.page.items])
    return NotificationsOut(**base.model_dump(), unread=result.unread)


@router.get("/unread-count", response_model=UnreadOut, summary="Cuántas tengo sin leer")
def unread_count(actor: ActorDep, container: ContainerDep) -> UnreadOut:
    return UnreadOut(unread=container.count_unread_notifications().execute(actor))


@router.post(
    "/read",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Marcar como leídas (ids; sin ids, todas)",
)
def mark_read(body: MarkReadIn, actor: ActorDep, container: ContainerDep) -> Response:
    container.mark_notifications_read().execute(actor, body.ids)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
