from app.application.commands.context import RequestContext
from app.application.commands.forms import CreateProductTypeCommand, UpdateProductTypeCommand
from app.application.dto.page import Page, PageRequest
from app.application.ports.repositories.unit_of_work import UnitOfWorkFactory
from app.application.ports.services.clock import Clock
from app.application.use_cases.audit_helper import record_audit
from app.domain.entities.audit_entry import JsonValue
from app.domain.entities.product_type import ProductType
from app.domain.enums.audit_action import AuditAction
from app.domain.enums.permission import Permission
from app.domain.exceptions.errors import ProductTypeNotFound
from app.domain.forms.definition import FormVersion
from app.domain.services.authorizer import has_permission, require_permission
from app.domain.value_objects.actor import Actor


class CreateProductType:
    """Registra un tipo de producto nuevo y le deja listo su primer borrador de formulario."""

    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    def execute(
        self, actor: Actor, command: CreateProductTypeCommand, ctx: RequestContext
    ) -> tuple[ProductType, FormVersion]:
        require_permission(actor, Permission.MANAGE_FORMS)
        now = self._clock.now()
        product_type = ProductType.create(
            command.code, command.name, command.description, now, command.folder_name
        )
        with self._uow_factory() as uow:
            uow.product_types.add(product_type)  # DuplicateProductType si el código existe
            assert product_type.id is not None
            draft = uow.forms.add(FormVersion.new(product_type.id, 1, actor.user_id, now))
            detail: dict[str, JsonValue] = {"product_type_id": product_type.id}
            record_audit(
                uow,
                ctx,
                now,
                AuditAction.PRODUCT_TYPE_CREATED,
                actor_id=actor.user_id,
                entity_id=None,
                detail={**detail, "code": product_type.code},
            )
            record_audit(
                uow,
                ctx,
                now,
                AuditAction.FORM_DRAFT_CREATED,
                actor_id=actor.user_id,
                entity_id=None,
                detail={**detail, "form_version_id": draft.id, "version_number": 1},
            )
            uow.commit()
        return product_type, draft


class UpdateProductType:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    def execute(
        self, actor: Actor, command: UpdateProductTypeCommand, ctx: RequestContext
    ) -> ProductType:
        require_permission(actor, Permission.MANAGE_FORMS)
        now = self._clock.now()
        with self._uow_factory() as uow:
            product_type = uow.product_types.get(command.product_type_id)
            if product_type is None:
                raise ProductTypeNotFound("Tipo de producto no encontrado")
            changed: list[JsonValue] = [
                name
                for name, value in (
                    ("name", command.name),
                    ("description", command.description),
                    ("is_active", command.is_active),
                )
                if value is not None
            ]
            product_type.update(
                now,
                name=command.name,
                description=command.description,
                is_active=command.is_active,
            )
            uow.product_types.save(product_type)
            record_audit(
                uow,
                ctx,
                now,
                AuditAction.PRODUCT_TYPE_UPDATED,
                actor_id=actor.user_id,
                entity_id=None,
                detail={"product_type_id": command.product_type_id, "changed": changed},
            )
            uow.commit()
            return product_type


class ListProductTypes:
    """Quien gestiona formularios ve todos los tipos; el resto solo los activos."""

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, actor: Actor, page: PageRequest) -> Page[ProductType]:
        require_permission(actor, Permission.VIEW_FORMS)
        only_active = not has_permission(actor.role, Permission.MANAGE_FORMS)
        with self._uow_factory() as uow:
            return uow.product_types.list(only_active, page)
