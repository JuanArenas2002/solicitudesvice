import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    SmallInteger,
    String,
    Uuid,
    column,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base, timestamptz


class UserModel(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(column("email") == func.lower(column("email")), name="email_lowercase"),
        CheckConstraint(
            func.length(func.trim(column("first_name"))) > 0, name="first_name_not_blank"
        ),
        CheckConstraint(
            func.length(func.trim(column("last_name"))) > 0, name="last_name_not_blank"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("roles.id", ondelete="RESTRICT"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=true())
    created_at: Mapped[datetime] = timestamptz(server_now=True)
    updated_at: Mapped[datetime] = timestamptz(server_now=True)
    last_login_at: Mapped[datetime | None] = timestamptz()
