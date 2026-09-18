import uuid
from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Identity, Index, SmallInteger, String, Uuid, column
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.expression import ColumnClause

from app.infrastructure.database.base import Base, timestamptz

_entity_id: ColumnClause[uuid.UUID] = column("entity_id")
_actor_id: ColumnClause[uuid.UUID] = column("actor_id")


class AuditLogModel(Base):
    """Append-only. Reforzar en BD: el rol de la aplicación sin UPDATE/DELETE (ver DATABASE.md).

    El tipo de entidad no se guarda por fila: lo determina la acción (audit_actions.entity_type).
    """

    __tablename__ = "audit_logs"
    __table_args__ = (
        # Parciales: muchas filas (p. ej. login fallido) no tienen entidad o actor.
        Index(
            "ix_audit_logs_entity",
            "entity_id",
            "occurred_at",
            postgresql_where=_entity_id.is_not(None),
        ),
        Index(
            "ix_audit_logs_actor",
            "actor_id",
            "occurred_at",
            postgresql_where=_actor_id.is_not(None),
        ),
        Index("ix_audit_logs_action", "action_id", "occurred_at"),
        # BRIN: la tabla solo crece en orden temporal; índice minúsculo para rangos de fechas.
        Index("ix_audit_logs_occurred_at", "occurred_at", postgresql_using="brin"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    occurred_at: Mapped[datetime] = timestamptz(server_now=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT")
    )
    action_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("audit_actions.id", ondelete="RESTRICT")
    )
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    correlation_id: Mapped[str | None] = mapped_column(String(64))
    ip_address: Mapped[str | None] = mapped_column(INET)
    detail: Mapped[dict[str, object]] = mapped_column(JSONB)
