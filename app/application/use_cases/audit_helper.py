from datetime import datetime
from uuid import UUID

from app.application.commands.context import RequestContext
from app.application.ports.repositories.unit_of_work import UnitOfWork
from app.domain.entities.audit_entry import AuditEntry, JsonValue
from app.domain.enums.audit_action import AuditAction


def record_audit(
    uow: UnitOfWork,
    ctx: RequestContext,
    now: datetime,
    action: AuditAction,
    *,
    actor_id: UUID | None,
    entity_id: UUID | None,
    detail: dict[str, JsonValue] | None = None,
) -> None:
    """Escribe la auditoría en la MISMA transacción que la operación auditada."""
    uow.audit.add(
        AuditEntry(
            action=action,
            occurred_at=now,
            actor_id=actor_id,
            entity_id=entity_id,
            correlation_id=ctx.correlation_id,
            ip_address=ctx.ip_address,
            detail=detail or {},
        )
    )
