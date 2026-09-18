import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    Uuid,
    column,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.forms import field_types as ft
from app.infrastructure.database.base import Base, timestamptz
from app.infrastructure.database.catalog import FIELD_TYPE_IDS


class RequestAttachmentModel(Base):
    """Metadatos del adjunto; el archivo vive en el storage, nunca en PostgreSQL."""

    __tablename__ = "request_attachments"
    __table_args__ = (
        # El soporte es de un campo SUPPORT de la MISMA versión de formulario que su solicitud.
        ForeignKeyConstraint(
            ["request_id", "form_version_id"],
            ["research_product_requests.id", "research_product_requests.form_version_id"],
            name="fk_request_attachments_request_id_research_product_requests",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["field_id", "form_version_id", "field_type_id"],
            ["form_fields.id", "form_fields.form_version_id", "form_fields.field_type_id"],
            name="fk_request_attachments_field_id_form_fields",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            column("field_type_id") == FIELD_TYPE_IDS[ft.SUPPORT], name="field_is_support"
        ),
        CheckConstraint(column("file_size") > 0, name="file_size_positive"),
        CheckConstraint(
            func.length(func.trim(column("file_name"))) > 0, name="file_name_not_blank"
        ),
        CheckConstraint(column("sha256").regexp_match("^[0-9a-f]{64}$"), name="sha256_format"),
        UniqueConstraint("request_id", "sha256", name="uq_request_attachments_request_sha256"),
        Index("ix_request_attachments_request_id", "request_id"),
        Index("ix_request_attachments_field_id", "field_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    request_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    form_version_id: Mapped[int] = mapped_column(Integer)
    field_id: Mapped[int] = mapped_column(Integer)
    field_type_id: Mapped[int] = mapped_column(SmallInteger)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT")
    )
    file_name: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(500), unique=True)
    mime_type: Mapped[str] = mapped_column(String(100))
    file_size: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = timestamptz(server_now=True)
