from app.application.commands.context import RequestContext
from app.application.commands.forms import ReplaceFormDraftCommand
from app.application.dto.forms import FormVersionSummary
from app.application.ports.repositories.unit_of_work import UnitOfWork, UnitOfWorkFactory
from app.application.ports.services.clock import Clock
from app.application.use_cases.audit_helper import record_audit
from app.domain.enums.audit_action import AuditAction
from app.domain.enums.permission import Permission
from app.domain.exceptions.errors import FormDraftExists, FormVersionNotFound, ProductTypeNotFound
from app.domain.forms.definition import FormVersion
from app.domain.services.authorizer import require_permission
from app.domain.value_objects.actor import Actor


def _load_version(uow: UnitOfWork, version_id: int, *, for_update: bool = False) -> FormVersion:
    version = uow.forms.get(version_id, for_update=for_update)
    if version is None:
        raise FormVersionNotFound("Versión de formulario no encontrada")
    return version


class CreateFormDraft:
    """Abre un borrador nuevo copiando la versión publicada (o vacío si aún no hay ninguna)."""

    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    def execute(self, actor: Actor, product_type_id: int, ctx: RequestContext) -> FormVersion:
        require_permission(actor, Permission.MANAGE_FORMS)
        now = self._clock.now()
        with self._uow_factory() as uow:
            if uow.product_types.get(product_type_id) is None:
                raise ProductTypeNotFound("Tipo de producto no encontrado")
            if uow.forms.get_draft(product_type_id) is not None:
                raise FormDraftExists("Ya existe un borrador: edítelo o publíquelo")
            number = uow.forms.next_version_number(product_type_id)
            published = uow.forms.get_published(product_type_id)
            draft = (
                published.copy_as_draft(number, actor.user_id, now)
                if published
                else FormVersion.new(product_type_id, number, actor.user_id, now)
            )
            saved = uow.forms.add(draft)
            record_audit(
                uow,
                ctx,
                now,
                AuditAction.FORM_DRAFT_CREATED,
                actor_id=actor.user_id,
                entity_id=None,
                detail={
                    "product_type_id": product_type_id,
                    "form_version_id": saved.id,
                    "version_number": number,
                },
            )
            uow.commit()
            return saved


class ReplaceFormDraft:
    """Guarda el documento completo del borrador (validado por el dominio)."""

    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    def execute(
        self, actor: Actor, command: ReplaceFormDraftCommand, ctx: RequestContext
    ) -> FormVersion:
        require_permission(actor, Permission.MANAGE_FORMS)
        now = self._clock.now()
        with self._uow_factory() as uow:
            version = _load_version(uow, command.version_id, for_update=True)
            version.replace_structure(command.sections)  # FormNotEditable / InvalidValue
            saved = uow.forms.save(version)
            record_audit(
                uow,
                ctx,
                now,
                AuditAction.FORM_DRAFT_SAVED,
                actor_id=actor.user_id,
                entity_id=None,
                detail={
                    "form_version_id": command.version_id,
                    "sections": len(saved.sections),
                    "fields": sum(len(s.fields) for s in saved.sections),
                },
            )
            uow.commit()
            return saved


class PublishForm:
    """Publica el borrador y retira la versión publicada anterior, todo en una transacción."""

    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    def execute(self, actor: Actor, version_id: int, ctx: RequestContext) -> FormVersion:
        require_permission(actor, Permission.MANAGE_FORMS)
        now = self._clock.now()
        with self._uow_factory() as uow:
            version = _load_version(uow, version_id, for_update=True)
            version.publish(now)  # FormNotEditable si no es borrador; InvalidValue si está vacío
            replaced = uow.forms.get_published(version.product_type_id, for_update=True)
            if replaced is not None:
                replaced.retire(now)
                uow.forms.save(replaced)  # se retira primero: la BD admite una sola publicada
            saved = uow.forms.save(version)
            record_audit(
                uow,
                ctx,
                now,
                AuditAction.FORM_PUBLISHED,
                actor_id=actor.user_id,
                entity_id=None,
                detail={
                    "product_type_id": version.product_type_id,
                    "form_version_id": version_id,
                    "version_number": version.version_number,
                    "replaced_version_number": replaced.version_number if replaced else None,
                },
            )
            uow.commit()
            return saved


class GetFormVersion:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, actor: Actor, version_id: int) -> FormVersion:
        require_permission(actor, Permission.MANAGE_FORMS)
        with self._uow_factory() as uow:
            return _load_version(uow, version_id)


class ListFormVersions:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, actor: Actor, product_type_id: int) -> list[FormVersionSummary]:
        require_permission(actor, Permission.MANAGE_FORMS)
        with self._uow_factory() as uow:
            if uow.product_types.get(product_type_id) is None:
                raise ProductTypeNotFound("Tipo de producto no encontrado")
            return uow.forms.list_versions(product_type_id)


class GetPublishedForm:
    """El formulario vigente de un producto (lo que ve el mentor al iniciar una solicitud)."""

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, actor: Actor, product_type_id: int) -> FormVersion:
        require_permission(actor, Permission.VIEW_FORMS)
        with self._uow_factory() as uow:
            product_type = uow.product_types.get(product_type_id)
            if product_type is None or not product_type.is_active:
                raise ProductTypeNotFound("Tipo de producto no encontrado")
            published = uow.forms.get_published(product_type_id)
            if published is None:
                raise FormVersionNotFound("Este producto aún no tiene un formulario publicado")
            return published
