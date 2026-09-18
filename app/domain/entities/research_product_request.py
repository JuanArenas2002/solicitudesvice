from dataclasses import dataclass, field
from datetime import datetime
from typing import Self
from uuid import UUID, uuid4

from app.domain.entities.request_correction import RequestCorrection
from app.domain.entities.status_change import StatusChange
from app.domain.enums.permission import Permission
from app.domain.enums.request_action import RequestAction
from app.domain.enums.request_status import RequestStatus
from app.domain.exceptions.errors import (
    ConcurrentModification,
    Forbidden,
    IncompleteProduct,
    InvalidRequestState,
    InvalidStatusTransition,
    InvalidValue,
)
from app.domain.products.base import ProductDetail
from app.domain.services.authorizer import require_permission
from app.domain.services.request_workflow import EDITABLE_STATUSES, TRANSITIONS, TransitionRule
from app.domain.value_objects.actor import Actor
from app.domain.value_objects.request_number import RequestNumber
from app.domain.value_objects.text import clean_optional

REASON_MAX = 2000
_NEEDS_REVIEW_DATE = frozenset(
    {
        RequestStatus.CORRECCION_SOLICITADA,
        RequestStatus.REENVIADA,
        RequestStatus.APROBADA,
        RequestStatus.RECHAZADA,
    }
)


@dataclass(eq=False)
class ResearchProductRequest:
    """Agregado raíz. El estado solo cambia mediante los métodos de transición."""

    id: UUID
    request_number: RequestNumber
    mentor_id: UUID
    form_version_id: int
    product_type_id: int
    status: RequestStatus
    created_at: datetime
    updated_at: datetime
    reviewer_id: UUID | None = None
    submitted_at: datetime | None = None
    reviewed_at: datetime | None = None
    version: int = 1
    corrections: list[RequestCorrection] = field(default_factory=list)

    # ---- creación ----
    @classmethod
    def create_draft(
        cls,
        *,
        actor: Actor,
        request_number: RequestNumber,
        form_version_id: int,
        product_type_id: int,
        now: datetime,
    ) -> tuple[Self, StatusChange]:
        require_permission(actor, Permission.CREATE_REQUEST)
        request = cls(
            id=uuid4(),
            request_number=request_number,
            mentor_id=actor.user_id,
            form_version_id=form_version_id,
            product_type_id=product_type_id,
            status=RequestStatus.BORRADOR,
            created_at=now,
            updated_at=now,
        )
        change = StatusChange(request.id, None, RequestStatus.BORRADOR, actor.user_id, now)
        return request, change

    # ---- consultas ----
    @property
    def open_correction(self) -> RequestCorrection | None:
        return next((c for c in self.corrections if c.is_open), None)

    # ---- edición (los datos del producto viven en su propio detalle) ----
    def ensure_editable_by(self, actor: Actor) -> None:
        require_permission(actor, Permission.EDIT_OWN_REQUEST)
        self._ensure_owner(actor)
        if self.status not in EDITABLE_STATUSES:
            raise InvalidRequestState(f"La solicitud no es editable en estado {self.status}")

    def register_edit(self, actor: Actor, now: datetime, expected_version: int) -> None:
        """Valida permiso/estado/versión y marca la raíz como modificada (sube `version`)."""
        self.ensure_editable_by(actor)
        if expected_version != self.version:
            raise ConcurrentModification("La solicitud fue modificada por otra operación")
        self.updated_at = now

    # ---- transiciones ----
    def submit(self, actor: Actor, now: datetime, product: ProductDetail) -> StatusChange:
        rule, _ = self._authorize(RequestAction.SUBMIT, actor, None)
        self._ensure_complete(product)
        self.submitted_at = now
        return self._move(rule, actor, now, None)

    def start_review(self, actor: Actor, now: datetime) -> StatusChange:
        rule, _ = self._authorize(RequestAction.START_REVIEW, actor, None)
        self.reviewer_id = actor.user_id
        return self._move(rule, actor, now, None)

    def request_correction(self, actor: Actor, now: datetime, description: str) -> StatusChange:
        rule, reason = self._authorize(RequestAction.REQUEST_CORRECTION, actor, description)
        assert reason is not None  # reason_required lo garantiza
        self.corrections.append(RequestCorrection.open(self.id, actor.user_id, reason, now))
        self.reviewed_at = now
        return self._move(rule, actor, now, reason)

    def resubmit(self, actor: Actor, now: datetime, product: ProductDetail) -> StatusChange:
        rule, _ = self._authorize(RequestAction.RESUBMIT, actor, None)
        correction = self.open_correction
        if correction is None:
            raise InvalidRequestState("No hay una corrección abierta que resolver")
        self._ensure_complete(product)
        correction.resolve(now)
        self.submitted_at = now
        return self._move(rule, actor, now, None)

    def approve(self, actor: Actor, now: datetime, reason: str | None = None) -> StatusChange:
        rule, clean_reason = self._authorize(RequestAction.APPROVE, actor, reason)
        self.reviewed_at = now
        return self._move(rule, actor, now, clean_reason)

    def reject(self, actor: Actor, now: datetime, reason: str) -> StatusChange:
        rule, clean_reason = self._authorize(RequestAction.REJECT, actor, reason)
        self.reviewed_at = now
        return self._move(rule, actor, now, clean_reason)

    def change_status(
        self, actor: Actor, now: datetime, target: RequestStatus, reason: str | None
    ) -> StatusChange:
        """Cambio manual del personal administrativo a cualquier estado, siempre con motivo.

        Sale del flujo normal: no valida la máquina de estados, pero conserva las invariantes que
        la base de datos exige (revisor y fecha de revisión según el estado, una sola corrección
        abierta) y queda en el historial y en la auditoría.
        """
        require_permission(actor, Permission.CHANGE_REQUEST_STATUS)
        clean_reason = clean_optional(reason, "reason", REASON_MAX)
        if clean_reason is None:
            raise InvalidValue("El motivo del cambio es obligatorio", field="reason")
        if self.status is RequestStatus.BORRADOR or target is RequestStatus.BORRADOR:
            raise InvalidStatusTransition(
                "El borrador es privado del mentor: no se cambia ni se vuelve a él"
            )
        if target is self.status:
            raise InvalidStatusTransition("La solicitud ya está en ese estado")
        open_correction = self.open_correction
        if target is RequestStatus.CORRECCION_SOLICITADA:
            if open_correction is None:
                self.corrections.append(
                    RequestCorrection.open(self.id, actor.user_id, clean_reason, now)
                )
        elif open_correction is not None:
            open_correction.resolve(now)
        if target in _NEEDS_REVIEW_DATE:
            self.reviewed_at = (
                (self.reviewed_at or now) if target is RequestStatus.REENVIADA else now
            )
        self.reviewer_id = (
            None if target is RequestStatus.ENVIADA else (self.reviewer_id or actor.user_id)
        )
        previous = self.status
        self.status = target
        self.updated_at = now
        return StatusChange(self.id, previous, target, actor.user_id, now, clean_reason)

    # ---- internos ----
    def _ensure_owner(self, actor: Actor) -> None:
        if actor.user_id != self.mentor_id:
            raise Forbidden("Solo el mentor dueño puede realizar esta operación")

    def _authorize(
        self, action: RequestAction, actor: Actor, reason: str | None
    ) -> tuple[TransitionRule, str | None]:
        """Valida permiso, propiedad, estado y motivo SIN mutar nada."""
        rule = TRANSITIONS[action]
        require_permission(actor, rule.permission)
        if rule.owner_only:
            self._ensure_owner(actor)
        if self.status not in rule.sources:
            raise InvalidStatusTransition(f"No se puede ejecutar {action} desde {self.status}")
        clean_reason = clean_optional(reason, "reason", REASON_MAX)
        if rule.reason_required and clean_reason is None:
            raise InvalidValue("El motivo es obligatorio", field="reason")
        return rule, clean_reason

    def _ensure_complete(self, product: ProductDetail) -> None:
        if product.request_id != self.id:
            raise InvalidValue("El producto no pertenece a esta solicitud", field="product")
        missing = product.missing_for_submission()
        if missing:
            raise IncompleteProduct(missing)

    def _move(
        self, rule: TransitionRule, actor: Actor, now: datetime, reason: str | None
    ) -> StatusChange:
        previous = self.status
        self.status = rule.target
        self.updated_at = now
        return StatusChange(self.id, previous, rule.target, actor.user_id, now, reason)
