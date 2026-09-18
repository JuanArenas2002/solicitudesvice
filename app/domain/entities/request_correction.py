from dataclasses import dataclass, field
from datetime import datetime
from typing import Self
from uuid import UUID, uuid4

from app.domain.enums.correction_status import CorrectionStatus
from app.domain.exceptions.errors import InvalidRequestState
from app.domain.value_objects.text import clean_required

DESCRIPTION_MAX = 2000


@dataclass(eq=False)
class RequestCorrection:
    request_id: UUID
    requested_by: UUID
    description: str
    created_at: datetime
    status: CorrectionStatus = CorrectionStatus.ABIERTA
    resolved_at: datetime | None = None
    id: UUID = field(default_factory=uuid4)

    @classmethod
    def open(cls, request_id: UUID, requested_by: UUID, description: str, now: datetime) -> Self:
        return cls(
            request_id=request_id,
            requested_by=requested_by,
            description=clean_required(description, "description", DESCRIPTION_MAX),
            created_at=now,
        )

    @property
    def is_open(self) -> bool:
        return self.status is CorrectionStatus.ABIERTA

    def resolve(self, now: datetime) -> None:
        if not self.is_open:
            raise InvalidRequestState("La corrección ya está resuelta")
        self.status = CorrectionStatus.RESUELTA
        self.resolved_at = now
