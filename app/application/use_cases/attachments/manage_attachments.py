import logging
from collections.abc import Iterator
from dataclasses import dataclass
from uuid import UUID

from app.application.commands.context import RequestContext
from app.application.ports.repositories.unit_of_work import UnitOfWorkFactory
from app.application.ports.services.clock import Clock
from app.application.ports.services.file_storage import FileStorage
from app.application.use_cases.audit_helper import record_audit
from app.application.use_cases.requests.queries import load_request
from app.domain.entities.attachment import Attachment
from app.domain.enums.audit_action import AuditAction
from app.domain.enums.permission import Permission
from app.domain.exceptions.errors import (
    AttachmentLimitReached,
    AttachmentNotFound,
    CedulaLocked,
    DuplicateAttachment,
    Forbidden,
    FormVersionNotFound,
    InvalidValue,
    ProductTypeNotFound,
)
from app.domain.services.access_policy import ensure_can_view
from app.domain.services.attachment_rules import (
    MAX_FILES_PER_REQUEST,
    unique_file_name,
    validate_upload,
)
from app.domain.services.authorizer import has_permission, require_permission
from app.domain.value_objects.actor import Actor

log = logging.getLogger("app.attachments")


class UploadAttachment:
    """Guarda un soporte en  <cédula>/<producto>/Solicitud <N>/<archivo>.

    Todo ocurre con la solicitud bloqueada: así dos cargas simultáneas no se pisan el nombre ni
    el número de carpeta. Si la base falla después de escribir el archivo, el archivo se borra.
    """

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        storage: FileStorage,
        max_bytes: int,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._storage = storage
        self._max_bytes = max_bytes

    def execute(
        self,
        actor: Actor,
        request_id: UUID,
        field_key: str,
        file_name: str,
        content: bytes,
        ctx: RequestContext,
    ) -> Attachment:
        validated = validate_upload(file_name, content, self._max_bytes)  # antes de tocar la BD
        now = self._clock.now()
        with self._uow_factory() as uow:
            request = load_request(uow, request_id, for_update=True)
            ensure_can_view(actor, request)  # otro mentor: 404
            require_permission(actor, Permission.MANAGE_OWN_ATTACHMENTS)
            request.ensure_editable_by(actor)  # dueño y estado editable

            form = uow.forms.get(request.form_version_id)
            if form is None:  # pragma: no cover - el FK lo impide
                raise FormVersionNotFound("Formulario de la solicitud no encontrado")
            field = form.field(field_key)
            if field is None or field.id is None or not field.is_support:
                raise InvalidValue(
                    f"'{field_key}' no es un campo de soporte de este formulario",
                    field="field_key",
                )
            extension = validated.file_name.rpartition(".")[2].lower()
            if extension not in field.allowed_types:
                raise InvalidValue(
                    f"«{field.label}» solo admite: {', '.join(field.allowed_types)}",
                    field="file",
                )
            cedula = uow.answers.load(request.id, form).cedula
            if cedula is None:
                raise InvalidValue(
                    "Diligencie la cédula antes de adjuntar soportes: define su carpeta",
                    field="cedula",
                )
            folder = uow.folders.get(request.id)
            if folder is None:
                product = uow.product_types.get(form.product_type_id)
                if product is None:  # pragma: no cover - el FK lo impide
                    raise ProductTypeNotFound("Producto de la solicitud no encontrado")
                folder = uow.folders.create(
                    request.id, cedula, form.product_type_id, product.folder_name, now
                )
            elif folder.cedula != cedula:  # pragma: no cover - la cédula se bloquea al adjuntar
                raise CedulaLocked("La cédula ya no coincide con la carpeta de los soportes")

            existing = uow.attachments.list(request.id)
            if len(existing) >= MAX_FILES_PER_REQUEST:
                raise AttachmentLimitReached(
                    f"Una solicitud admite como máximo {MAX_FILES_PER_REQUEST} soportes"
                )
            if any(a.sha256 == validated.sha256 for a in existing):
                raise DuplicateAttachment("Este archivo ya fue adjuntado a la solicitud")

            name = unique_file_name(validated.file_name, [a.file_name for a in existing])
            attachment = Attachment(
                request_id=request.id,
                field_id=field.id,
                field_key=field.key,
                uploaded_by=actor.user_id,
                file_name=name,
                storage_key=f"{folder.relative_path}/{name}",
                mime_type=validated.mime_type,
                file_size=validated.size,
                sha256=validated.sha256,
                created_at=now,
            )
            self._storage.save(attachment.storage_key, content)
            try:
                uow.attachments.add(attachment)
                record_audit(
                    uow,
                    ctx,
                    now,
                    AuditAction.ATTACHMENT_UPLOADED,
                    actor_id=actor.user_id,
                    entity_id=attachment.id,
                    detail={
                        "request_id": str(request.id),
                        "file_name": name,
                        "field": field.key,
                        "size": validated.size,
                        "sha256": validated.sha256,
                        "folder": folder.relative_path,
                    },
                )
                uow.commit()
            except BaseException:
                self._storage.delete(attachment.storage_key)  # sin huérfanos si falla la BD
                raise
            return attachment


class ListAttachments:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, actor: Actor, request_id: UUID) -> list[Attachment]:
        with self._uow_factory() as uow:
            request = load_request(uow, request_id)
            ensure_can_view(actor, request)
            return uow.attachments.list(request_id)


@dataclass(frozen=True, slots=True)
class Download:
    attachment: Attachment
    content: Iterator[bytes]


class DownloadAttachment:
    """Descarga: el dueño de la solicitud o quien tenga DOWNLOAD_ATTACHMENTS (ADMINISTRATIVO)."""

    def __init__(self, uow_factory: UnitOfWorkFactory, storage: FileStorage) -> None:
        self._uow_factory = uow_factory
        self._storage = storage

    def execute(self, actor: Actor, request_id: UUID, attachment_id: UUID) -> Download:
        with self._uow_factory() as uow:
            request = load_request(uow, request_id)
            ensure_can_view(actor, request)
            is_owner = request.mentor_id == actor.user_id
            if not is_owner and not has_permission(actor.role, Permission.DOWNLOAD_ATTACHMENTS):
                raise Forbidden("No tiene permiso para descargar soportes")
            attachment = uow.attachments.get(request_id, attachment_id)
            if attachment is None:
                raise AttachmentNotFound("Soporte no encontrado")
        try:
            return Download(attachment, self._storage.open(attachment.storage_key))
        except FileNotFoundError as error:
            log.error("Soporte en BD sin archivo", extra={"attachment_id": str(attachment_id)})
            raise AttachmentNotFound("El archivo del soporte no está disponible") from error


class DeleteAttachment:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock, storage: FileStorage) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._storage = storage

    def execute(
        self, actor: Actor, request_id: UUID, attachment_id: UUID, ctx: RequestContext
    ) -> None:
        now = self._clock.now()
        with self._uow_factory() as uow:
            request = load_request(uow, request_id, for_update=True)
            ensure_can_view(actor, request)
            require_permission(actor, Permission.MANAGE_OWN_ATTACHMENTS)
            request.ensure_editable_by(actor)
            attachment = uow.attachments.get(request_id, attachment_id)
            if attachment is None:
                raise AttachmentNotFound("Soporte no encontrado")
            uow.attachments.delete(attachment.id)
            record_audit(
                uow,
                ctx,
                now,
                AuditAction.ATTACHMENT_DELETED,
                actor_id=actor.user_id,
                entity_id=attachment.id,
                detail={
                    "request_id": str(request_id),
                    "file_name": attachment.file_name,
                    "sha256": attachment.sha256,
                },
            )
            uow.commit()
        # Después de confirmar: si esto falla queda un archivo huérfano (se registra), nunca un
        # registro apuntando a un archivo inexistente.
        try:
            self._storage.delete(attachment.storage_key)
        except OSError:
            log.exception("No se pudo borrar el archivo", extra={"key": attachment.storage_key})
