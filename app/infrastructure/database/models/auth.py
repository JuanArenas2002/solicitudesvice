import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Uuid, and_, column, or_
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.expression import ColumnClause

from app.infrastructure.database.base import Base, timestamptz

_revoked_at: ColumnClause[object] = column("revoked_at")


class AuthSessionModel(Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        CheckConstraint(
            or_(
                and_(_revoked_at.is_(None), column("revoked_reason").is_(None)),
                and_(_revoked_at.is_not(None), column("revoked_reason").is_not(None)),
            ),
            name="revocation_consistent",
        ),
        # Parcial: solo sesiones vivas (revocar todas las de un usuario al desactivarlo).
        Index("ix_auth_sessions_user_active", "user_id", postgresql_where=_revoked_at.is_(None)),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = timestamptz(server_now=True)
    expires_at: Mapped[datetime] = timestamptz()
    revoked_at: Mapped[datetime | None] = timestamptz()
    revoked_reason: Mapped[str | None] = mapped_column(String(50))


class RefreshTokenModel(Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (
        CheckConstraint(
            column("token_hash").regexp_match("^[0-9a-f]{64}$"), name="token_hash_sha256"
        ),
        Index("ix_refresh_tokens_session_id", "session_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("auth_sessions.id", ondelete="RESTRICT")
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = timestamptz(server_now=True)
    expires_at: Mapped[datetime] = timestamptz()
    used_at: Mapped[datetime | None] = timestamptz()
