from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, File, Form, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.domain.entities.attachment import Attachment
from app.interfaces.api.dependencies import ActorDep, ContainerDep, ContextDep

router = APIRouter(prefix="/requests/{request_id}/attachments", tags=["attachments"])


class AttachmentOut(BaseModel):
    id: UUID
    field_key: str
    file_name: str
    mime_type: str
    file_size: int
    sha256: str
    folder: str
    uploaded_by: UUID
    created_at: str

    @classmethod
    def of(cls, a: Attachment) -> "AttachmentOut":
        return cls(
            id=a.id,
            field_key=a.field_key,
            file_name=a.file_name,
            mime_type=a.mime_type,
            file_size=a.file_size,
            sha256=a.sha256,
            folder=a.storage_key.rpartition("/")[0],
            uploaded_by=a.uploaded_by,
            created_at=a.created_at.isoformat(),
        )


@router.post(
    "",
    response_model=AttachmentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Adjuntar un soporte a un campo de soporte (multipart: 'field_key' y 'file')",
)
def upload(
    request_id: UUID,
    field_key: Annotated[str, Form(max_length=60, description="Clave del campo SUPPORT")],
    file: Annotated[UploadFile, File(description="Solo los tipos que admite ese campo")],
    actor: ActorDep,
    container: ContainerDep,
    ctx: ContextDep,
) -> AttachmentOut:
    limit = container.settings.attachment_max_bytes
    content = file.file.read(limit + 1)  # +1: basta para saber que se pasó, sin leer todo
    attachment = container.upload_attachment().execute(
        actor, request_id, field_key, file.filename or "", content, ctx
    )
    return AttachmentOut.of(attachment)


@router.get("", response_model=list[AttachmentOut], summary="Soportes de la solicitud")
def list_attachments(
    request_id: UUID, actor: ActorDep, container: ContainerDep
) -> list[AttachmentOut]:
    return [AttachmentOut.of(a) for a in container.list_attachments().execute(actor, request_id)]


@router.get("/{attachment_id}/download", summary="Descargar un soporte")
def download(
    request_id: UUID, attachment_id: UUID, actor: ActorDep, container: ContainerDep
) -> StreamingResponse:
    result = container.download_attachment().execute(actor, request_id, attachment_id)
    name = result.attachment.file_name
    return StreamingResponse(
        result.content,
        media_type=result.attachment.mime_type,
        headers={
            # Se fuerza la descarga (nunca se muestra dentro de la página) y se evita el "sniffing".
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}",
            "Content-Length": str(result.attachment.file_size),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.delete(
    "/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar un soporte (solo el dueño, en borrador o corrección)",
)
def delete(
    request_id: UUID,
    attachment_id: UUID,
    actor: ActorDep,
    container: ContainerDep,
    ctx: ContextDep,
) -> Response:
    container.delete_attachment().execute(actor, request_id, attachment_id, ctx)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
