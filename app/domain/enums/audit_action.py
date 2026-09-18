from enum import StrEnum


class AuditCategory(StrEnum):
    SECURITY = "SECURITY"
    REQUESTS = "REQUESTS"
    CONFIGURATION = "CONFIGURATION"


class AuditAction(StrEnum):
    LOGIN_SUCCEEDED = "LOGIN_SUCCEEDED"
    LOGIN_FAILED = "LOGIN_FAILED"
    LOGOUT = "LOGOUT"
    SESSION_REVOKED = "SESSION_REVOKED"
    REFRESH_REUSE_DETECTED = "REFRESH_REUSE_DETECTED"
    PASSWORD_CHANGED = "PASSWORD_CHANGED"
    PASSWORD_RESET = "PASSWORD_RESET"
    USER_CREATED = "USER_CREATED"
    USER_UPDATED = "USER_UPDATED"
    USER_ACTIVATED = "USER_ACTIVATED"
    USER_DEACTIVATED = "USER_DEACTIVATED"
    USER_PRODUCTS_ASSIGNED = "USER_PRODUCTS_ASSIGNED"

    REQUEST_CREATED = "REQUEST_CREATED"
    REQUEST_UPDATED = "REQUEST_UPDATED"
    REQUEST_SUBMITTED = "REQUEST_SUBMITTED"
    REVIEW_STARTED = "REVIEW_STARTED"
    CORRECTION_REQUESTED = "CORRECTION_REQUESTED"
    REQUEST_RESUBMITTED = "REQUEST_RESUBMITTED"
    REQUEST_APPROVED = "REQUEST_APPROVED"
    REQUEST_REJECTED = "REQUEST_REJECTED"
    REQUEST_STATUS_CHANGED = "REQUEST_STATUS_CHANGED"
    ATTACHMENT_UPLOADED = "ATTACHMENT_UPLOADED"
    ATTACHMENT_DELETED = "ATTACHMENT_DELETED"

    PRODUCT_TYPE_CREATED = "PRODUCT_TYPE_CREATED"
    PRODUCT_TYPE_UPDATED = "PRODUCT_TYPE_UPDATED"
    FORM_DRAFT_CREATED = "FORM_DRAFT_CREATED"
    FORM_DRAFT_SAVED = "FORM_DRAFT_SAVED"
    FORM_PUBLISHED = "FORM_PUBLISHED"

    @property
    def category(self) -> AuditCategory:
        if self in _CONFIGURATION_ACTIONS:
            return AuditCategory.CONFIGURATION
        return AuditCategory.REQUESTS if self in _REQUEST_ACTIONS else AuditCategory.SECURITY

    @property
    def entity_type(self) -> str:
        """Tipo de entidad sobre la que actúa (entity_id de la bitácora), derivado de la acción."""
        return _ENTITY_TYPES.get(self, "request" if self in _REQUEST_ACTIONS else "session")


_REQUEST_ACTIONS = frozenset(
    {
        AuditAction.REQUEST_CREATED,
        AuditAction.REQUEST_UPDATED,
        AuditAction.REQUEST_SUBMITTED,
        AuditAction.REVIEW_STARTED,
        AuditAction.CORRECTION_REQUESTED,
        AuditAction.REQUEST_RESUBMITTED,
        AuditAction.REQUEST_APPROVED,
        AuditAction.REQUEST_REJECTED,
        AuditAction.REQUEST_STATUS_CHANGED,
        AuditAction.ATTACHMENT_UPLOADED,
        AuditAction.ATTACHMENT_DELETED,
    }
)

_ENTITY_TYPES = {
    AuditAction.PASSWORD_CHANGED: "user",
    AuditAction.PASSWORD_RESET: "user",
    AuditAction.USER_CREATED: "user",
    AuditAction.USER_UPDATED: "user",
    AuditAction.USER_ACTIVATED: "user",
    AuditAction.USER_DEACTIVATED: "user",
    AuditAction.USER_PRODUCTS_ASSIGNED: "user",
    AuditAction.ATTACHMENT_UPLOADED: "attachment",
    AuditAction.ATTACHMENT_DELETED: "attachment",
    AuditAction.PRODUCT_TYPE_CREATED: "product_type",
    AuditAction.PRODUCT_TYPE_UPDATED: "product_type",
    AuditAction.FORM_DRAFT_CREATED: "form_version",
    AuditAction.FORM_DRAFT_SAVED: "form_version",
    AuditAction.FORM_PUBLISHED: "form_version",
}

_CONFIGURATION_ACTIONS = frozenset(
    {
        AuditAction.USER_PRODUCTS_ASSIGNED,
        AuditAction.PRODUCT_TYPE_CREATED,
        AuditAction.PRODUCT_TYPE_UPDATED,
        AuditAction.FORM_DRAFT_CREATED,
        AuditAction.FORM_DRAFT_SAVED,
        AuditAction.FORM_PUBLISHED,
    }
)
