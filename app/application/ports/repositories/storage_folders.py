from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.domain.entities.storage_folder import StorageFolder


class StorageFolderRepository(Protocol):
    def get(self, request_id: UUID) -> StorageFolder | None: ...

    def create(
        self,
        request_id: UUID,
        cedula: str,
        product_type_id: int,
        product_folder: str,
        now: datetime,
    ) -> StorageFolder:
        """Asigna el siguiente 'Solicitud N' de esa cédula y producto (seguro ante concurrencia)."""
        ...
