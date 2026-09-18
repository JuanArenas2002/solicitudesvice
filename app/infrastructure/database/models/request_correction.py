import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    SmallInteger,
    Text,
    Uuid,
    and_,
    column,
    func,
    or_,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.expression import ColumnClause

from app.domain.enums.correction_status import CorrectionStatus as C
from app.infrastructure.database.base import Base, timestamptz
from app.infrastructure.database.catalog import CORRECTION_STATUS_IDS as ID

_status: ColumnClause[int] = column("status_id")


class RequestCorrectionModel(Base):
    __tablename__ = "request_corrections"
    __table_args__ = (
        CheckConstraint(
            func.length(func.trim(column("description"))) > 0, name="description_not_blank"
        ),
        CheckConstraint(
            or_(
                and_(_status == ID[C.ABIERTA], column("resolved_at").is_(None)),
                and_(_status == ID[C.RESUELTA], column("resolved_at").is_not(None)),
            ),
            name="resolved_at_matches_status",
        ),
        Index("ix_request_corrections_request_id", "request_id"),
        # A lo sumo una corrección abierta por solicitud, garantizado por la BD.
        Index(
            "uq_request_corrections_one_open",
            "request_id",
            unique=True,
            postgresql_where=_status == ID[C.ABIERTA],
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    request_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("research_product_requests.id", ondelete="RESTRICT")
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT")
    )
    description: Mapped[str] = mapped_column(Text)
    status_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("correction_statuses.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = timestamptz(server_now=True)
    resolved_at: Mapped[datetime | None] = timestamptz()
