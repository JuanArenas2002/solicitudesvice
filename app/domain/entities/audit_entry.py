from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from app.domain.enums.audit_action import AuditAction
from app.domain.exceptions.errors import InvalidValue

type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]

# Fragmentos de clave que jamás deben llegar a la bitácora.
_FORBIDDEN_KEY_PARTS = ("password", "token", "secret", "authorization", "cookie")


@dataclass(frozen=True, slots=True)
class AuditEntry:
    """Evento de auditoría, append-only: no existe operación de actualización ni borrado."""

    action: AuditAction
    occurred_at: datetime
    actor_id: UUID | None = None
    entity_id: UUID | None = None
    correlation_id: str | None = None
    ip_address: str | None = None
    detail: dict[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _assert_no_secrets(self.detail)


def _assert_no_secrets(value: JsonValue | Mapping[str, JsonValue]) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if any(part in key.lower() for part in _FORBIDDEN_KEY_PARTS):
                raise InvalidValue(f"La bitácora no admite datos sensibles ({key})", field="detail")
            _assert_no_secrets(item)
    elif isinstance(value, list):
        for item in value:
            _assert_no_secrets(item)
