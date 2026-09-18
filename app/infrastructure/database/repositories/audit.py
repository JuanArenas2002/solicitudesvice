from sqlalchemy.orm import Session

from app.domain.entities.audit_entry import AuditEntry
from app.infrastructure.database.catalog import AUDIT_ACTION_IDS
from app.infrastructure.database.models.audit_log import AuditLogModel


class SqlAlchemyAuditLogRepository:
    """Solo inserta: no hay operación de actualización ni de borrado."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, entry: AuditEntry) -> None:
        self._session.add(
            AuditLogModel(
                occurred_at=entry.occurred_at,
                actor_id=entry.actor_id,
                action_id=AUDIT_ACTION_IDS[entry.action],
                entity_id=entry.entity_id,
                correlation_id=entry.correlation_id,
                ip_address=entry.ip_address,
                detail=dict(entry.detail),
            )
        )
        self._session.flush()
