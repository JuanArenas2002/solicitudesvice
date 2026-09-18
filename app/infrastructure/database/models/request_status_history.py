import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Identity,
    Index,
    SmallInteger,
    Text,
    Uuid,
    column,
    func,
    or_,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.expression import ColumnClause

from app.domain.enums.request_status import RequestStatus as S
from app.infrastructure.database.base import Base, timestamptz
from app.infrastructure.database.catalog import REQUEST_STATUS_IDS as ID

_previous: ColumnClause[int] = column("previous_status_id")
_new: ColumnClause[int] = column("new_status_id")


class RequestStatusHistoryModel(Base):
    """Append-only: solo inserta y consulta. PK secuencial: inserciones sin fragmentar el índice."""

    __tablename__ = "request_status_history"
    __table_args__ = (
        CheckConstraint(or_(_previous.is_(None), _previous != _new), name="status_changes"),
        CheckConstraint(
            or_(_previous.is_not(None), _new == ID[S.BORRADOR]), name="creation_is_draft"
        ),
        CheckConstraint(
            or_(column("reason").is_(None), func.length(func.trim(column("reason"))) > 0),
            name="reason_not_blank",
        ),
        Index("ix_request_status_history_request_created", "request_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    request_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("research_product_requests.id", ondelete="RESTRICT")
    )
    previous_status_id: Mapped[int | None] = mapped_column(
        SmallInteger, ForeignKey("request_statuses.id", ondelete="RESTRICT")
    )
    new_status_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("request_statuses.id", ondelete="RESTRICT")
    )
    changed_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"))
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = timestamptz(server_now=True)
