import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    Uuid,
    and_,
    column,
    or_,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.expression import ColumnClause

from app.domain.enums.request_status import RequestStatus as S
from app.domain.value_objects.request_number import REQUEST_NUMBER_PATTERN
from app.infrastructure.database.base import Base, timestamptz
from app.infrastructure.database.catalog import REQUEST_STATUS_IDS as ID

_status: ColumnClause[int] = column("status_id")
_draft = ID[S.BORRADOR]
_unreviewed = [ID[S.BORRADOR], ID[S.ENVIADA]]
_review_round_closed = [
    ID[S.CORRECCION_SOLICITADA],
    ID[S.REENVIADA],
    ID[S.APROBADA],
    ID[S.RECHAZADA],
]


class ResearchProductRequestModel(Base):
    __tablename__ = "research_product_requests"
    __table_args__ = (
        CheckConstraint(
            column("request_number").regexp_match(REQUEST_NUMBER_PATTERN),
            name="request_number_format",
        ),
        CheckConstraint(
            or_(
                and_(_status == _draft, column("submitted_at").is_(None)),
                and_(_status != _draft, column("submitted_at").is_not(None)),
            ),
            name="submitted_at_matches_status",
        ),
        CheckConstraint(
            or_(
                and_(_status.in_(_unreviewed), column("reviewer_id").is_(None)),
                and_(_status.not_in(_unreviewed), column("reviewer_id").is_not(None)),
            ),
            name="reviewer_matches_status",
        ),
        CheckConstraint(
            or_(_status.not_in(_review_round_closed), column("reviewed_at").is_not(None)),
            name="reviewed_at_required",
        ),
        CheckConstraint(column("version") >= 1, name="version_positive"),
        Index("ix_requests_mentor_created", "mentor_id", "created_at"),
        Index("ix_requests_status_submitted", "status_id", "submitted_at"),
        Index("ix_requests_created_at", "created_at"),
        Index("ix_requests_form_version", "form_version_id"),
        # Objetivo del FK compuesto de request_answers: la respuesta usa la versión de su solicitud.
        UniqueConstraint("id", "form_version_id", name="uq_requests_id_form_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    request_number: Mapped[str] = mapped_column(String(15), unique=True)
    mentor_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"))
    form_version_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("form_versions.id", ondelete="RESTRICT")
    )
    status_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("request_statuses.id", ondelete="RESTRICT")
    )
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT")
    )
    submitted_at: Mapped[datetime | None] = timestamptz()
    reviewed_at: Mapped[datetime | None] = timestamptz()
    # Optimistic locking: SQLAlchemy lo incrementa en cada UPDATE (StaleDataError si cambió).
    version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = timestamptz(server_now=True)
    updated_at: Mapped[datetime] = timestamptz(server_now=True)

    __mapper_args__ = {"version_id_col": version}
