import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    SmallInteger,
    Text,
    Uuid,
    column,
    func,
    or_,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base, timestamptz


class NotificationModel(Base):
    """Aviso para un usuario cuando otra persona cambia el estado de su solicitud."""

    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(
            or_(
                column("reason").is_(None),
                func.length(func.trim(column("reason"))) > 0,
            ),
            name="reason_not_blank",
        ),
        Index("ix_notifications_user_created", "user_id", "created_at"),
        Index(
            "ix_notifications_unread",
            "user_id",
            postgresql_where=column("read_at").is_(None),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"))
    request_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("research_product_requests.id", ondelete="RESTRICT")
    )
    status_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("request_statuses.id", ondelete="RESTRICT")
    )
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = timestamptz(server_now=True)
    read_at: Mapped[datetime | None] = timestamptz()
