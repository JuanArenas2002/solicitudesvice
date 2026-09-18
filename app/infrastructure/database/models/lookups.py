from sqlalchemy import ForeignKey, SmallInteger, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class _Lookup:
    """Catálogo: id SMALLINT fijo (lo siembra la migración) + código único legible."""

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False)
    code: Mapped[str] = mapped_column(String(40), unique=True)


class RoleModel(_Lookup, Base):
    __tablename__ = "roles"


class RequestStatusModel(_Lookup, Base):
    __tablename__ = "request_statuses"


class CorrectionStatusModel(_Lookup, Base):
    __tablename__ = "correction_statuses"


class FormStatusModel(_Lookup, Base):
    __tablename__ = "form_statuses"


class ValueKindModel(_Lookup, Base):
    __tablename__ = "value_kinds"


class FieldTypeModel(_Lookup, Base):
    """Tipo de campo de formulario y en qué columna tipada se guardan sus respuestas."""

    __tablename__ = "field_types"
    __table_args__ = (
        # Objetivo del FK compuesto de request_answers (tipo <-> clase de valor coherentes).
        UniqueConstraint("id", "value_kind_id", name="uq_field_types_id_value_kind"),
    )

    value_kind_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("value_kinds.id", ondelete="RESTRICT")
    )


class DocumentTypeModel(_Lookup, Base):
    """Tipo de documento (extensión) que un campo de soporte puede admitir."""

    __tablename__ = "document_types"


class AuditCategoryModel(_Lookup, Base):
    __tablename__ = "audit_categories"


class AuditActionModel(_Lookup, Base):
    __tablename__ = "audit_actions"

    category_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("audit_categories.id", ondelete="RESTRICT")
    )
    entity_type: Mapped[str] = mapped_column(String(30))
