from typing import Protocol
from uuid import UUID

from app.domain.entities.attachment import Attachment


class AttachmentRepository(Protocol):
    def add(self, attachment: Attachment) -> None: ...

    def get(self, request_id: UUID, attachment_id: UUID) -> Attachment | None: ...

    def list(self, request_id: UUID) -> list[Attachment]:
        """En orden de carga."""
        ...

    def delete(self, attachment_id: UUID) -> None: ...
