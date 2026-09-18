from uuid import UUID

from sqlalchemy import Select, delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.entities.attachment import Attachment
from app.domain.exceptions.errors import DuplicateAttachment
from app.domain.forms.field_types import SUPPORT
from app.infrastructure.database.catalog import FIELD_TYPE_IDS
from app.infrastructure.database.models.form import FormFieldModel
from app.infrastructure.database.models.request_attachment import RequestAttachmentModel


def _entity(m: RequestAttachmentModel, field_key: str) -> Attachment:
    return Attachment(
        id=m.id,
        request_id=m.request_id,
        field_id=m.field_id,
        field_key=field_key,
        uploaded_by=m.uploaded_by,
        file_name=m.file_name,
        storage_key=m.storage_key,
        mime_type=m.mime_type,
        file_size=m.file_size,
        sha256=m.sha256,
        created_at=m.created_at,
    )


class SqlAlchemyAttachmentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, attachment: Attachment) -> None:
        self._session.add(
            RequestAttachmentModel(
                id=attachment.id,
                request_id=attachment.request_id,
                form_version_id=self._version_of(attachment.field_id),
                field_id=attachment.field_id,
                field_type_id=FIELD_TYPE_IDS[SUPPORT],
                uploaded_by=attachment.uploaded_by,
                file_name=attachment.file_name,
                storage_key=attachment.storage_key,
                mime_type=attachment.mime_type,
                file_size=attachment.file_size,
                sha256=attachment.sha256,
                created_at=attachment.created_at,
            )
        )
        try:
            self._session.flush()
        except IntegrityError as error:
            diag = getattr(error.orig, "diag", None)
            if getattr(diag, "constraint_name", None) == "uq_request_attachments_request_sha256":
                raise DuplicateAttachment("Este archivo ya fue adjuntado a la solicitud") from error
            raise

    def _version_of(self, field_id: int) -> int:
        version_id = self._session.scalar(
            select(FormFieldModel.form_version_id).where(FormFieldModel.id == field_id)
        )
        if version_id is None:  # pragma: no cover - el caso de uso ya validó el campo
            raise LookupError(f"Campo {field_id} no existe")
        return version_id

    def get(self, request_id: UUID, attachment_id: UUID) -> Attachment | None:
        row = self._session.execute(
            self._select().where(
                RequestAttachmentModel.id == attachment_id,
                RequestAttachmentModel.request_id
                == request_id,  # el adjunto debe ser de la solicitud
            )
        ).one_or_none()
        return _entity(row[0], row[1]) if row else None

    def list(self, request_id: UUID) -> list[Attachment]:
        rows = self._session.execute(
            self._select()
            .where(RequestAttachmentModel.request_id == request_id)
            .order_by(RequestAttachmentModel.created_at, RequestAttachmentModel.id)
        ).all()
        return [_entity(model, key) for model, key in rows]

    @staticmethod
    def _select() -> Select[tuple[RequestAttachmentModel, str]]:
        return select(RequestAttachmentModel, FormFieldModel.key).join(
            FormFieldModel, FormFieldModel.id == RequestAttachmentModel.field_id
        )

    def delete(self, attachment_id: UUID) -> None:
        self._session.execute(
            delete(RequestAttachmentModel).where(RequestAttachmentModel.id == attachment_id)
        )
        self._session.flush()
