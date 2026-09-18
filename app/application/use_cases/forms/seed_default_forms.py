from app.application.commands.context import RequestContext
from app.application.ports.repositories.unit_of_work import UnitOfWorkFactory
from app.application.ports.services.clock import Clock
from app.application.seed.article_form import (
    ARTICLE_CODE,
    ARTICLE_DESCRIPTION,
    ARTICLE_FOLDER,
    ARTICLE_NAME,
    ARTICLE_SECTIONS,
)
from app.application.use_cases.audit_helper import record_audit
from app.domain.entities.product_type import ProductType
from app.domain.enums.audit_action import AuditAction
from app.domain.enums.permission import Permission
from app.domain.forms.definition import FormVersion
from app.domain.services.authorizer import require_permission
from app.domain.value_objects.actor import Actor


class SeedDefaultForms:
    """Carga el formulario inicial de "Artículo científico". Idempotente y atómico."""

    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    def execute(self, actor: Actor, ctx: RequestContext) -> bool:
        """Devuelve True si cargó algo y False si ya existía un formulario publicado."""
        require_permission(actor, Permission.MANAGE_FORMS)
        now = self._clock.now()
        with self._uow_factory() as uow:
            product_type = uow.product_types.get_by_code(ARTICLE_CODE)
            if product_type is not None and product_type.id is not None:
                if uow.forms.get_published(product_type.id) is not None:
                    return False
            else:
                product_type = ProductType.create(
                    ARTICLE_CODE, ARTICLE_NAME, ARTICLE_DESCRIPTION, now, ARTICLE_FOLDER
                )
                uow.product_types.add(product_type)
                record_audit(
                    uow,
                    ctx,
                    now,
                    AuditAction.PRODUCT_TYPE_CREATED,
                    actor_id=actor.user_id,
                    entity_id=None,
                    detail={"product_type_id": product_type.id, "code": ARTICLE_CODE},
                )
            assert product_type.id is not None

            version = uow.forms.get_draft(product_type.id) or FormVersion.new(
                product_type.id,
                uow.forms.next_version_number(product_type.id),
                actor.user_id,
                now,
            )
            version.replace_structure(ARTICLE_SECTIONS)
            version.publish(now)
            saved = uow.forms.add(version) if version.id is None else uow.forms.save(version)
            record_audit(
                uow,
                ctx,
                now,
                AuditAction.FORM_PUBLISHED,
                actor_id=actor.user_id,
                entity_id=None,
                detail={
                    "product_type_id": product_type.id,
                    "form_version_id": saved.id,
                    "version_number": saved.version_number,
                    "seed": True,
                },
            )
            uow.commit()
            return True
