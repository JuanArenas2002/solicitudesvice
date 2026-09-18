"""Importar este paquete registra todos los modelos en Base.metadata (lo usa Alembic)."""

from app.infrastructure.database.base import Base
from app.infrastructure.database.models.audit_log import AuditLogModel
from app.infrastructure.database.models.auth import AuthSessionModel, RefreshTokenModel
from app.infrastructure.database.models.form import (
    FormFieldDocumentTypeModel,
    FormFieldModel,
    FormFieldOptionModel,
    FormSectionModel,
    FormVersionModel,
)
from app.infrastructure.database.models.lookups import (
    AuditActionModel,
    AuditCategoryModel,
    CorrectionStatusModel,
    DocumentTypeModel,
    FieldTypeModel,
    FormStatusModel,
    RequestStatusModel,
    RoleModel,
    ValueKindModel,
)
from app.infrastructure.database.models.notification import NotificationModel
from app.infrastructure.database.models.product_type import ProductTypeModel
from app.infrastructure.database.models.request_answer import RequestAnswerModel
from app.infrastructure.database.models.request_attachment import RequestAttachmentModel
from app.infrastructure.database.models.request_correction import RequestCorrectionModel
from app.infrastructure.database.models.request_counter import RequestCounterModel
from app.infrastructure.database.models.request_status_history import RequestStatusHistoryModel
from app.infrastructure.database.models.research_request import ResearchProductRequestModel
from app.infrastructure.database.models.storage import StorageCounterModel, StorageFolderModel
from app.infrastructure.database.models.user import UserModel
from app.infrastructure.database.models.user_product_assignment import UserProductAssignmentModel

__all__ = [
    "StorageCounterModel",
    "StorageFolderModel",
    "FieldTypeModel",
    "NotificationModel",
    "DocumentTypeModel",
    "FormFieldDocumentTypeModel",
    "UserProductAssignmentModel",
    "FormFieldModel",
    "FormFieldOptionModel",
    "FormSectionModel",
    "FormStatusModel",
    "FormVersionModel",
    "RequestAnswerModel",
    "ValueKindModel",
    "AuditActionModel",
    "AuditCategoryModel",
    "CorrectionStatusModel",
    "ProductTypeModel",
    "RequestStatusModel",
    "RoleModel",
    "AuditLogModel",
    "AuthSessionModel",
    "Base",
    "RefreshTokenModel",
    "RequestAttachmentModel",
    "RequestCorrectionModel",
    "RequestCounterModel",
    "RequestStatusHistoryModel",
    "ResearchProductRequestModel",
    "UserModel",
]
