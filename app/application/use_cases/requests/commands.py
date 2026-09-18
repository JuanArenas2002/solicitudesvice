from collections.abc import Callable, Mapping
from uuid import UUID

from app.application.commands.context import RequestContext
from app.application.dto.requests import RequestDetail
from app.application.ports.repositories.unit_of_work import UnitOfWork, UnitOfWorkFactory
from app.application.ports.services.clock import Clock
from app.application.ports.services.journals import JournalCatalog
from app.application.use_cases.audit_helper import record_audit
from app.application.use_cases.journals import verify_issns
from app.application.use_cases.requests.queries import build_detail, load_filled, load_request
from app.domain.entities.audit_entry import JsonValue
from app.domain.entities.notification import Notification
from app.domain.entities.research_product_request import ResearchProductRequest
from app.domain.entities.status_change import StatusChange
from app.domain.enums.audit_action import AuditAction
from app.domain.enums.permission import Permission
from app.domain.enums.request_status import RequestStatus
from app.domain.exceptions.errors import CedulaLocked, FormVersionNotFound, ProductTypeNotFound
from app.domain.forms.filled_form import FilledForm
from app.domain.services.access_policy import ensure_can_view
from app.domain.services.authorizer import require_permission
from app.domain.value_objects.actor import Actor


class CreateRequest:
    """Inicia una solicitud (borrador) con el formulario publicado del producto elegido."""

    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    def execute(self, actor: Actor, product_type_id: int, ctx: RequestContext) -> RequestDetail:
        require_permission(actor, Permission.CREATE_REQUEST)  # antes de gastar un número
        now = self._clock.now()
        with self._uow_factory() as uow:
            product_type = uow.product_types.get(product_type_id)
            if product_type is None or not product_type.is_active:
                raise ProductTypeNotFound("Tipo de producto no encontrado")
            form = uow.forms.get_published(product_type_id)
            if form is None or form.id is None:
                raise FormVersionNotFound("Este producto aún no tiene un formulario publicado")
            request, change = ResearchProductRequest.create_draft(
                actor=actor,
                request_number=uow.request_numbers.next(now.year),
                form_version_id=form.id,
                product_type_id=product_type_id,
                now=now,
            )
            uow.requests.add(request)
            uow.history.add(change)
            record_audit(
                uow,
                ctx,
                now,
                AuditAction.REQUEST_CREATED,
                actor_id=actor.user_id,
                entity_id=request.id,
                detail={
                    "request_number": str(request.request_number),
                    "product_type_id": product_type_id,
                    "form_version_id": form.id,
                },
            )
            uow.commit()
            return build_detail(uow, request)


class UpdateAnswers:
    """Guarda respuestas parciales. Exige la `version` que el cliente vio (optimistic locking)."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        journals: JournalCatalog | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._journals = journals

    def execute(
        self,
        actor: Actor,
        request_id: UUID,
        changes: Mapping[str, object],
        expected_version: int,
        ctx: RequestContext,
    ) -> RequestDetail:
        now = self._clock.now()
        with self._uow_factory() as uow:
            request = load_request(uow, request_id, for_update=True)
            ensure_can_view(actor, request)
            # permiso, dueño, estado editable y versión; también marca la raíz como modificada
            request.register_edit(actor, now, expected_version)
            form = uow.forms.get(request.form_version_id)
            if form is None:  # pragma: no cover - el FK lo impide
                raise FormVersionNotFound("Formulario de la solicitud no encontrado")
            current = uow.answers.load(request.id, form)
            updated = current.apply(changes)  # todo o nada: InvalidValue si algo no valida
            if updated.cedula != current.cedula and uow.folders.get(request.id) is not None:
                raise CedulaLocked(
                    "La cédula no se puede cambiar: ya hay soportes en su carpeta. "
                    "Elimine los soportes o inicie otra solicitud."
                )
            changed: list[JsonValue] = [*current.changed_keys(updated)]
            # solo los ISSN que cambiaron; si el catálogo no responde, el borrador se guarda igual
            verify_issns(self._journals, updated, {str(k) for k in changed}, strict=False)
            if changed:
                uow.answers.replace(updated)
            uow.requests.save(request)
            record_audit(
                uow,
                ctx,
                now,
                AuditAction.REQUEST_UPDATED,
                actor_id=actor.user_id,
                entity_id=request.id,
                detail={"changed": changed},  # solo claves de campo, nunca los valores
            )
            uow.commit()
            return build_detail(uow, request)


class _Transition:
    """Plantilla común: bloquear, verificar visibilidad, aplicar el dominio y dejar rastro.

    Historial, auditoría y cambio de estado se confirman juntos o no se confirma nada.
    """

    audit_action: AuditAction

    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    def _run(
        self,
        actor: Actor,
        request_id: UUID,
        ctx: RequestContext,
        transition: Callable[[ResearchProductRequest, UnitOfWork], StatusChange],
    ) -> RequestDetail:
        now = self._clock.now()
        with self._uow_factory() as uow:
            request = load_request(uow, request_id, for_update=True)  # serializa doble acción
            ensure_can_view(actor, request)
            change = transition(request, uow)  # el dominio valida rol, dueño y estado
            uow.requests.save(request)
            uow.history.add(change)
            assert change.previous_status is not None
            if actor.user_id != request.mentor_id:  # el mentor ya sabe lo que él mismo hizo
                uow.notifications.add(
                    Notification(
                        user_id=request.mentor_id,
                        request_id=request.id,
                        request_number=str(request.request_number),
                        status=change.new_status,
                        created_at=now,
                        reason=change.reason,
                    )
                )
            record_audit(
                uow,
                ctx,
                now,
                self.audit_action,
                actor_id=actor.user_id,
                entity_id=request.id,
                detail={"from": change.previous_status.value, "to": change.new_status.value},
            )
            uow.commit()
            return build_detail(uow, request)

    def _filled(self, uow: UnitOfWork, request: ResearchProductRequest) -> FilledForm:
        form = uow.forms.get(request.form_version_id)
        if form is None:  # pragma: no cover - el FK lo impide
            raise FormVersionNotFound("Formulario de la solicitud no encontrado")
        return load_filled(uow, request, form)


class _VerifiesIssn(_Transition):
    """Al enviar, todos los ISSN se verifican en el catálogo de revistas (sin filas bloqueadas)."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        journals: JournalCatalog | None = None,
    ) -> None:
        super().__init__(uow_factory, clock)
        self._journals = journals

    def _verify_issns(self, actor: Actor, request_id: UUID) -> None:
        if self._journals is None:
            return
        with self._uow_factory() as uow:
            request = load_request(uow, request_id)
            ensure_can_view(actor, request)
            filled = self._filled(uow, request)
        verify_issns(self._journals, filled, None, strict=True)


class SubmitRequest(_VerifiesIssn):
    audit_action = AuditAction.REQUEST_SUBMITTED

    def execute(self, actor: Actor, request_id: UUID, ctx: RequestContext) -> RequestDetail:
        self._verify_issns(actor, request_id)
        now = self._clock.now()
        return self._run(
            actor,
            request_id,
            ctx,
            lambda request, uow: request.submit(actor, now, self._filled(uow, request)),
        )


class StartReview(_Transition):
    audit_action = AuditAction.REVIEW_STARTED

    def execute(self, actor: Actor, request_id: UUID, ctx: RequestContext) -> RequestDetail:
        now = self._clock.now()
        return self._run(
            actor, request_id, ctx, lambda request, uow: request.start_review(actor, now)
        )


class RequestCorrection(_Transition):
    audit_action = AuditAction.CORRECTION_REQUESTED

    def execute(
        self, actor: Actor, request_id: UUID, description: str, ctx: RequestContext
    ) -> RequestDetail:
        now = self._clock.now()
        return self._run(
            actor,
            request_id,
            ctx,
            lambda request, uow: request.request_correction(actor, now, description),
        )


class ResubmitRequest(_VerifiesIssn):
    audit_action = AuditAction.REQUEST_RESUBMITTED

    def execute(self, actor: Actor, request_id: UUID, ctx: RequestContext) -> RequestDetail:
        self._verify_issns(actor, request_id)
        now = self._clock.now()
        return self._run(
            actor,
            request_id,
            ctx,
            lambda request, uow: request.resubmit(actor, now, self._filled(uow, request)),
        )


class ApproveRequest(_Transition):
    audit_action = AuditAction.REQUEST_APPROVED

    def execute(
        self, actor: Actor, request_id: UUID, reason: str | None, ctx: RequestContext
    ) -> RequestDetail:
        now = self._clock.now()
        return self._run(
            actor, request_id, ctx, lambda request, uow: request.approve(actor, now, reason)
        )


class RejectRequest(_Transition):
    audit_action = AuditAction.REQUEST_REJECTED

    def execute(
        self, actor: Actor, request_id: UUID, reason: str, ctx: RequestContext
    ) -> RequestDetail:
        now = self._clock.now()
        return self._run(
            actor, request_id, ctx, lambda request, uow: request.reject(actor, now, reason)
        )


class ChangeRequestStatus(_Transition):
    """Cambio manual de estado del personal administrativo (con motivo; queda en el historial)."""

    audit_action = AuditAction.REQUEST_STATUS_CHANGED

    def execute(
        self,
        actor: Actor,
        request_id: UUID,
        target: RequestStatus,
        reason: str | None,
        ctx: RequestContext,
    ) -> RequestDetail:
        now = self._clock.now()
        return self._run(
            actor,
            request_id,
            ctx,
            lambda request, uow: request.change_status(actor, now, target, reason),
        )
