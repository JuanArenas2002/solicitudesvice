from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from app.domain.enums.permission import Permission
from app.domain.enums.request_action import RequestAction
from app.domain.enums.request_status import RequestStatus as S


@dataclass(frozen=True, slots=True)
class TransitionRule:
    sources: frozenset[S]
    target: S
    permission: Permission
    owner_only: bool = False
    reason_required: bool = False


# Máquina de estados explícita: cualquier (estado, acción) que no esté aquí es inválido.
TRANSITIONS: Mapping[RequestAction, TransitionRule] = MappingProxyType(
    {
        RequestAction.SUBMIT: TransitionRule(
            frozenset({S.BORRADOR}), S.ENVIADA, Permission.SUBMIT_OWN_REQUEST, owner_only=True
        ),
        RequestAction.START_REVIEW: TransitionRule(
            frozenset({S.ENVIADA, S.REENVIADA}), S.EN_REVISION, Permission.REVIEW_REQUEST
        ),
        RequestAction.REQUEST_CORRECTION: TransitionRule(
            frozenset({S.EN_REVISION}),
            S.CORRECCION_SOLICITADA,
            Permission.REQUEST_CORRECTION,
            reason_required=True,
        ),
        RequestAction.RESUBMIT: TransitionRule(
            frozenset({S.CORRECCION_SOLICITADA}),
            S.REENVIADA,
            Permission.SUBMIT_OWN_REQUEST,
            owner_only=True,
        ),
        RequestAction.APPROVE: TransitionRule(
            frozenset({S.EN_REVISION}), S.APROBADA, Permission.APPROVE_REQUEST
        ),
        RequestAction.REJECT: TransitionRule(
            frozenset({S.EN_REVISION}),
            S.RECHAZADA,
            Permission.REJECT_REQUEST,
            reason_required=True,
        ),
    }
)

# El dueño solo edita en estos estados; en ENVIADA/EN_REVISION/REENVIADA quedan congelados.
EDITABLE_STATUSES = frozenset({S.BORRADOR, S.CORRECCION_SOLICITADA})
