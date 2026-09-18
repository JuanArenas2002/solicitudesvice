"""Identificadores de las tablas de catálogo (roles, estados, tipos de campo, acciones).

Los catálogos son tablas normalizadas con PK SMALLINT (2 bytes: FK e índices compactos, joins
baratos). Sus filas las siembra la migración con estos mismos ids, fijos e inmutables; por eso
los repositorios convierten código<->id con estos mapas, sin consultar la BD en cada operación.
Un test verifica que la semilla de la migración coincide con este archivo.

Los tipos de producto NO están aquí: son datos que crean los administradores desde el sistema.
"""

from collections.abc import Mapping
from types import MappingProxyType

from app.domain.enums.audit_action import AuditAction as A
from app.domain.enums.audit_action import AuditCategory
from app.domain.enums.correction_status import CorrectionStatus
from app.domain.enums.form_status import FormStatus
from app.domain.enums.request_status import RequestStatus as S
from app.domain.enums.role import Role
from app.domain.enums.value_kind import ValueKind
from app.domain.forms import field_types as ft

ROLE_IDS: Mapping[Role, int] = MappingProxyType(
    {Role.ADMIN: 1, Role.ADMINISTRATIVO: 2, Role.MENTOR: 3}
)

REQUEST_STATUS_IDS: Mapping[S, int] = MappingProxyType(
    {
        S.BORRADOR: 1,
        S.ENVIADA: 2,
        S.EN_REVISION: 3,
        S.CORRECCION_SOLICITADA: 4,
        S.REENVIADA: 5,
        S.APROBADA: 6,
        S.RECHAZADA: 7,
    }
)

CORRECTION_STATUS_IDS: Mapping[CorrectionStatus, int] = MappingProxyType(
    {CorrectionStatus.ABIERTA: 1, CorrectionStatus.RESUELTA: 2}
)

FORM_STATUS_IDS: Mapping[FormStatus, int] = MappingProxyType(
    {FormStatus.BORRADOR: 1, FormStatus.PUBLICADA: 2, FormStatus.RETIRADA: 3}
)

VALUE_KIND_IDS: Mapping[ValueKind, int] = MappingProxyType(
    {
        ValueKind.TEXT: 1,
        ValueKind.NUMBER: 2,
        ValueKind.DATE: 3,
        ValueKind.BOOLEAN: 4,
        ValueKind.OPTION: 5,
        ValueKind.FILE: 6,
    }
)

# Código del tipo de campo -> id. Un tipo nuevo agrega aquí su id (y su fila en la migración).
FIELD_TYPE_IDS: Mapping[str, int] = MappingProxyType(
    {
        ft.TEXT: 1,
        ft.LONG_TEXT: 2,
        ft.INTEGER: 3,
        ft.DECIMAL: 4,
        ft.DATE: 5,
        ft.BOOLEAN: 6,
        ft.SINGLE_SELECT: 7,
        ft.MULTI_SELECT: 8,
        ft.URL: 9,
        ft.DOI: 10,
        ft.ISSN: 11,
        ft.EMAIL: 12,
        ft.CEDULA: 13,
        ft.SUPPORT: 14,
    }
)

# Tipos de documento que un campo de soporte puede admitir (código = extensión del archivo).
DOCUMENT_TYPE_IDS: Mapping[str, int] = MappingProxyType(
    {
        "pdf": 1,
        "png": 2,
        "jpg": 3,
        "jpeg": 4,
        "doc": 5,
        "docx": 6,
        "xls": 7,
        "xlsx": 8,
        "ppt": 9,
        "pptx": 10,
        "zip": 11,
    }
)

AUDIT_CATEGORY_IDS: Mapping[AuditCategory, int] = MappingProxyType(
    {AuditCategory.SECURITY: 1, AuditCategory.REQUESTS: 2, AuditCategory.CONFIGURATION: 3}
)

AUDIT_ACTION_IDS: Mapping[A, int] = MappingProxyType(
    {
        A.LOGIN_SUCCEEDED: 1,
        A.LOGIN_FAILED: 2,
        A.LOGOUT: 3,
        A.SESSION_REVOKED: 4,
        A.REFRESH_REUSE_DETECTED: 5,
        A.PASSWORD_CHANGED: 6,
        A.PASSWORD_RESET: 7,
        A.USER_CREATED: 8,
        A.USER_UPDATED: 9,
        A.USER_ACTIVATED: 10,
        A.USER_DEACTIVATED: 11,
        A.REQUEST_CREATED: 12,
        A.REQUEST_UPDATED: 13,
        A.REQUEST_SUBMITTED: 14,
        A.REVIEW_STARTED: 15,
        A.CORRECTION_REQUESTED: 16,
        A.REQUEST_RESUBMITTED: 17,
        A.REQUEST_APPROVED: 18,
        A.REQUEST_REJECTED: 19,
        A.ATTACHMENT_UPLOADED: 20,
        A.ATTACHMENT_DELETED: 21,
        A.PRODUCT_TYPE_CREATED: 22,
        A.PRODUCT_TYPE_UPDATED: 23,
        A.FORM_DRAFT_CREATED: 24,
        A.FORM_DRAFT_SAVED: 25,
        A.FORM_PUBLISHED: 26,
        A.USER_PRODUCTS_ASSIGNED: 27,
        A.REQUEST_STATUS_CHANGED: 28,
    }
)

ROLE_BY_ID: Mapping[int, Role] = MappingProxyType({i: r for r, i in ROLE_IDS.items()})
REQUEST_STATUS_BY_ID: Mapping[int, S] = MappingProxyType(
    {i: s for s, i in REQUEST_STATUS_IDS.items()}
)
FORM_STATUS_BY_ID: Mapping[int, FormStatus] = MappingProxyType(
    {i: s for s, i in FORM_STATUS_IDS.items()}
)
FIELD_TYPE_BY_ID: Mapping[int, str] = MappingProxyType({i: c for c, i in FIELD_TYPE_IDS.items()})
DOCUMENT_TYPE_BY_ID: Mapping[int, str] = MappingProxyType(
    {i: c for c, i in DOCUMENT_TYPE_IDS.items()}
)


def lookup_rows() -> dict[str, list[tuple[object, ...]]]:
    """Filas esperadas de cada catálogo, derivadas del dominio (verifican la semilla)."""
    return {
        "roles": [(i, r.value) for r, i in ROLE_IDS.items()],
        "request_statuses": [(i, s.value) for s, i in REQUEST_STATUS_IDS.items()],
        "correction_statuses": [(i, c.value) for c, i in CORRECTION_STATUS_IDS.items()],
        "form_statuses": [(i, s.value) for s, i in FORM_STATUS_IDS.items()],
        "value_kinds": [(i, k.value) for k, i in VALUE_KIND_IDS.items()],
        "field_types": [
            (i, code, VALUE_KIND_IDS[ft.FIELD_TYPES[code].kind])
            for code, i in FIELD_TYPE_IDS.items()
        ],
        "document_types": [(i, code) for code, i in DOCUMENT_TYPE_IDS.items()],
        "audit_categories": [(i, c.value) for c, i in AUDIT_CATEGORY_IDS.items()],
        "audit_actions": [
            (i, a.value, AUDIT_CATEGORY_IDS[a.category], a.entity_type)
            for a, i in AUDIT_ACTION_IDS.items()
        ],
    }
