from collections.abc import Collection
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.orm import Session

from app.application.dto.page import Page, PageRequest
from app.domain.entities.notification import Notification
from app.infrastructure.database.catalog import REQUEST_STATUS_BY_ID, REQUEST_STATUS_IDS
from app.infrastructure.database.models.notification import NotificationModel
from app.infrastructure.database.models.research_request import ResearchProductRequestModel


class SqlAlchemyNotificationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, notification: Notification) -> None:
        self._session.add(
            NotificationModel(
                id=notification.id,
                user_id=notification.user_id,
                request_id=notification.request_id,
                status_id=REQUEST_STATUS_IDS[notification.status],
                reason=notification.reason,
                created_at=notification.created_at,
                read_at=notification.read_at,
            )
        )
        self._session.flush()

    def list(self, user_id: UUID, unread_only: bool, page: PageRequest) -> Page[Notification]:
        n, r = NotificationModel, ResearchProductRequestModel
        query = (
            select(n, r.request_number).join(r, r.id == n.request_id).where(n.user_id == user_id)
        )
        if unread_only:
            query = query.where(n.read_at.is_(None))
        total = self._session.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = self._session.execute(
            query.order_by(n.created_at.desc(), n.id).limit(page.limit).offset(page.offset)
        ).all()
        items = tuple(
            Notification(
                id=m.id,
                user_id=m.user_id,
                request_id=m.request_id,
                request_number=number,
                status=REQUEST_STATUS_BY_ID[m.status_id],
                reason=m.reason,
                created_at=m.created_at,
                read_at=m.read_at,
            )
            for m, number in rows
        )
        return Page(items=items, total=total, page=page.page, page_size=page.page_size)

    def unread_count(self, user_id: UUID) -> int:
        return (
            self._session.scalar(
                select(func.count()).where(
                    NotificationModel.user_id == user_id, NotificationModel.read_at.is_(None)
                )
            )
            or 0
        )

    def mark_read(self, user_id: UUID, ids: Collection[UUID] | None, now: datetime) -> int:
        statement = (
            update(NotificationModel)
            .where(NotificationModel.user_id == user_id, NotificationModel.read_at.is_(None))
            .values(read_at=now)
        )
        if ids is not None:
            statement = statement.where(NotificationModel.id.in_(list(ids)))
        result = cast(CursorResult[Any], self._session.execute(statement))
        return result.rowcount or 0
