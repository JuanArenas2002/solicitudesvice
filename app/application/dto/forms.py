from dataclasses import dataclass
from datetime import datetime

from app.domain.enums.form_status import FormStatus


@dataclass(frozen=True, slots=True)
class FormVersionSummary:
    """Resumen de una versión de formulario (sin su estructura) para listados."""

    id: int
    version_number: int
    status: FormStatus
    created_at: datetime
    published_at: datetime | None
    retired_at: datetime | None
