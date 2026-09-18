from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.entities.status_change import StatusChange
from app.infrastructure.database.catalog import REQUEST_STATUS_BY_ID, REQUEST_STATUS_IDS
from app.infrastructure.database.models.request_status_history import RequestStatusHistoryModel


class SqlAlchemyStatusHistoryRepository:
    """Solo inserta y consulta: no hay operación de actualización ni de borrado."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, change: StatusChange) -> None:
        self._session.add(
            RequestStatusHistoryModel(
                request_id=change.request_id,
                previous_status_id=(
                    REQUEST_STATUS_IDS[change.previous_status] if change.previous_status else None
                ),
                new_status_id=REQUEST_STATUS_IDS[change.new_status],
                changed_by=change.changed_by,
                reason=change.reason,
                created_at=change.occurred_at,
            )
        )
        self._session.flush()

    def list(self, request_id: UUID) -> list[StatusChange]:
        rows = self._session.scalars(
            select(RequestStatusHistoryModel)
            .where(RequestStatusHistoryModel.request_id == request_id)
            .order_by(RequestStatusHistoryModel.id)
        ).all()
        return [
            StatusChange(
                request_id=r.request_id,
                previous_status=(
                    REQUEST_STATUS_BY_ID[r.previous_status_id]
                    if r.previous_status_id is not None
                    else None
                ),
                new_status=REQUEST_STATUS_BY_ID[r.new_status_id],
                changed_by=r.changed_by,
                occurred_at=r.created_at,
                reason=r.reason,
            )
            for r in rows
        ]
