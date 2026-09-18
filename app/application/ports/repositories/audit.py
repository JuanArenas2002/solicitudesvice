from typing import Protocol

from app.domain.entities.audit_entry import AuditEntry


class AuditLogRepository(Protocol):
    """Append-only: no existe operación de actualización ni de borrado."""

    def add(self, entry: AuditEntry) -> None: ...
