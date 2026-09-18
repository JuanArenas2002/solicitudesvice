from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from app.domain.exceptions.errors import InvalidValue
from app.domain.value_objects.text import clean_required

FILE_NAME_MAX = 255
STORAGE_KEY_MAX = 500
MIME_TYPE_MAX = 100


@dataclass(frozen=True, slots=True)
class Attachment:
    """Metadatos de un archivo; el contenido vive en el storage (no en PostgreSQL)."""

    request_id: UUID
    field_id: int
    field_key: str
    uploaded_by: UUID
    file_name: str
    storage_key: str
    mime_type: str
    file_size: int
    sha256: str
    created_at: datetime
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        clean_required(self.file_name, "file_name", FILE_NAME_MAX)
        clean_required(self.storage_key, "storage_key", STORAGE_KEY_MAX)
        clean_required(self.mime_type, "mime_type", MIME_TYPE_MAX)
        if self.file_size <= 0:
            raise InvalidValue("file_size debe ser mayor que cero", field="file_size")
        if len(self.sha256) != 64 or any(c not in "0123456789abcdef" for c in self.sha256):
            raise InvalidValue("sha256 inválido", field="sha256")
