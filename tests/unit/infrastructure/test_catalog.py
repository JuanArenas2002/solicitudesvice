from typing import Any

from app.domain.enums.audit_action import AuditAction, AuditCategory
from app.domain.enums.correction_status import CorrectionStatus
from app.domain.enums.form_status import FormStatus
from app.domain.enums.request_status import RequestStatus
from app.domain.enums.role import Role
from app.domain.enums.value_kind import ValueKind
from app.domain.forms.field_types import FIELD_TYPES
from app.infrastructure.database import catalog


def test_every_domain_member_has_a_unique_positive_smallint_id() -> None:
    pairs: list[tuple[Any, Any]] = [
        (Role, catalog.ROLE_IDS),
        (RequestStatus, catalog.REQUEST_STATUS_IDS),
        (CorrectionStatus, catalog.CORRECTION_STATUS_IDS),
        (FormStatus, catalog.FORM_STATUS_IDS),
        (ValueKind, catalog.VALUE_KIND_IDS),
        (AuditCategory, catalog.AUDIT_CATEGORY_IDS),
        (AuditAction, catalog.AUDIT_ACTION_IDS),
    ]
    for enum, ids in pairs:
        assert set(ids) == set(enum), enum.__name__  # ningún miembro sin id ni ids huérfanos
        values = list(ids.values())
        assert len(values) == len(set(values)), enum.__name__
        assert all(1 <= v <= 32767 for v in values), enum.__name__


def test_every_registered_field_type_has_a_catalog_id() -> None:
    """Un tipo de campo nuevo exige su id en el catálogo (y su fila en la migración)."""
    assert set(catalog.FIELD_TYPE_IDS) == set(FIELD_TYPES)
    assert len(set(catalog.FIELD_TYPE_IDS.values())) == len(FIELD_TYPES)
