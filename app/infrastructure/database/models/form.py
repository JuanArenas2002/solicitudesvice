import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    Uuid,
    and_,
    column,
    false,
    func,
    or_,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql.expression import ColumnClause

from app.domain.enums.form_status import FormStatus as F
from app.domain.forms.definition import (
    DESCRIPTION_MAX,
    HELP_MAX,
    KEY_PATTERN,
    LABEL_MAX,
    OPTION_VALUE_MAX,
    TITLE_MAX,
)
from app.infrastructure.database.base import Base, timestamptz
from app.infrastructure.database.catalog import FORM_STATUS_IDS as ID

_status: ColumnClause[int] = column("status_id")
_published_at: ColumnClause[datetime] = column("published_at")
_retired_at: ColumnClause[datetime] = column("retired_at")


class FormVersionModel(Base):
    __tablename__ = "form_versions"
    __table_args__ = (
        CheckConstraint(column("version_number") >= 1, name="version_number_positive"),
        CheckConstraint(
            or_(
                and_(_status == ID[F.BORRADOR], _published_at.is_(None), _retired_at.is_(None)),
                and_(_status == ID[F.PUBLICADA], _published_at.is_not(None), _retired_at.is_(None)),
                and_(
                    _status == ID[F.RETIRADA],
                    _published_at.is_not(None),
                    _retired_at.is_not(None),
                    _retired_at >= _published_at,
                ),
            ),
            name="dates_match_status",
        ),
        UniqueConstraint("product_type_id", "version_number", name="uq_form_versions_type_number"),
        # Como máximo una versión publicada y un borrador por tipo de producto (lo garantiza la BD).
        Index(
            "uq_form_versions_one_published",
            "product_type_id",
            unique=True,
            postgresql_where=_status == ID[F.PUBLICADA],
        ),
        Index(
            "uq_form_versions_one_draft",
            "product_type_id",
            unique=True,
            postgresql_where=_status == ID[F.BORRADOR],
        ),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(always=True), primary_key=True)
    product_type_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("product_types.id", ondelete="RESTRICT")
    )
    version_number: Mapped[int] = mapped_column(Integer)
    status_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("form_statuses.id", ondelete="RESTRICT")
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = timestamptz(server_now=True)
    published_at: Mapped[datetime | None] = timestamptz()
    retired_at: Mapped[datetime | None] = timestamptz()

    sections: Mapped[list["FormSectionModel"]] = relationship(
        order_by="FormSectionModel.position", cascade="all, delete-orphan", lazy="raise"
    )


class FormSectionModel(Base):
    __tablename__ = "form_sections"
    __table_args__ = (
        CheckConstraint(column("position") >= 1, name="position_positive"),
        CheckConstraint(func.length(func.trim(column("title"))) > 0, name="title_not_blank"),
        # Diferida: permite reordenar dentro de una transacción sin choques transitorios.
        UniqueConstraint(
            "form_version_id",
            "position",
            name="uq_form_sections_version_position",
            deferrable=True,
            initially="DEFERRED",
        ),
        # Objetivo del FK compuesto de form_fields: campo y sección son de la misma versión.
        UniqueConstraint("id", "form_version_id", name="uq_form_sections_id_version"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(always=True), primary_key=True)
    form_version_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("form_versions.id", ondelete="RESTRICT")
    )
    position: Mapped[int] = mapped_column(SmallInteger)
    title: Mapped[str] = mapped_column(String(TITLE_MAX))
    description: Mapped[str | None] = mapped_column(String(DESCRIPTION_MAX))

    fields: Mapped[list["FormFieldModel"]] = relationship(
        order_by="FormFieldModel.position", cascade="all, delete-orphan", lazy="raise"
    )


class FormFieldModel(Base):
    __tablename__ = "form_fields"
    __table_args__ = (
        ForeignKeyConstraint(
            ["section_id", "form_version_id"],
            ["form_sections.id", "form_sections.form_version_id"],
            name="fk_form_fields_section_id_form_sections",
            ondelete="RESTRICT",
        ),
        CheckConstraint(column("key").regexp_match(KEY_PATTERN), name="key_format"),
        CheckConstraint(column("position") >= 1, name="position_positive"),
        CheckConstraint(func.length(func.trim(column("label"))) > 0, name="label_not_blank"),
        CheckConstraint(column("min_length") >= 0, name="min_length_non_negative"),
        CheckConstraint(
            or_(
                column("max_length").is_(None),
                and_(
                    column("max_length") >= 0,
                    or_(
                        column("min_length").is_(None), column("max_length") >= column("min_length")
                    ),
                ),
            ),
            name="length_range_valid",
        ),
        CheckConstraint(
            or_(
                column("min_value").is_(None),
                column("max_value").is_(None),
                column("max_value") >= column("min_value"),
            ),
            name="value_range_valid",
        ),
        UniqueConstraint("form_version_id", "key", name="uq_form_fields_version_key"),
        UniqueConstraint(
            "section_id",
            "position",
            name="uq_form_fields_section_position",
            deferrable=True,
            initially="DEFERRED",
        ),
        # Objetivo del FK compuesto de request_answers: versión y tipo del campo coinciden.
        UniqueConstraint(
            "id", "form_version_id", "field_type_id", name="uq_form_fields_id_version_type"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(always=True), primary_key=True)
    form_version_id: Mapped[int] = mapped_column(Integer)
    section_id: Mapped[int] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(SmallInteger)
    key: Mapped[str] = mapped_column(String(60))
    label: Mapped[str] = mapped_column(String(LABEL_MAX))
    help_text: Mapped[str | None] = mapped_column(String(HELP_MAX))
    field_type_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("field_types.id", ondelete="RESTRICT")
    )
    required_to_submit: Mapped[bool] = mapped_column(Boolean, server_default=false())
    min_length: Mapped[int | None] = mapped_column(Integer)
    max_length: Mapped[int | None] = mapped_column(Integer)
    min_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    max_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))

    options: Mapped[list["FormFieldOptionModel"]] = relationship(
        order_by="FormFieldOptionModel.position", cascade="all, delete-orphan", lazy="raise"
    )
    document_types: Mapped[list["FormFieldDocumentTypeModel"]] = relationship(
        order_by="FormFieldDocumentTypeModel.document_type_id",
        cascade="all, delete-orphan",
        lazy="raise",
    )


class FormFieldDocumentTypeModel(Base):
    """Tipos de documento que admite un campo de soporte (uno por fila)."""

    __tablename__ = "form_field_document_types"

    field_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("form_fields.id", ondelete="RESTRICT"), primary_key=True
    )
    document_type_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("document_types.id", ondelete="RESTRICT"), primary_key=True
    )


class FormFieldOptionModel(Base):
    __tablename__ = "form_field_options"
    __table_args__ = (
        CheckConstraint(column("position") >= 1, name="position_positive"),
        CheckConstraint(func.length(func.trim(column("value"))) > 0, name="value_not_blank"),
        CheckConstraint(func.length(func.trim(column("label"))) > 0, name="label_not_blank"),
        UniqueConstraint("field_id", "value", name="uq_form_field_options_field_value"),
        UniqueConstraint(
            "field_id",
            "position",
            name="uq_form_field_options_field_position",
            deferrable=True,
            initially="DEFERRED",
        ),
        # Objetivo del FK compuesto de request_answers: la opción pertenece al campo respondido.
        UniqueConstraint("id", "field_id", name="uq_form_field_options_id_field"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(always=True), primary_key=True)
    field_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("form_fields.id", ondelete="RESTRICT")
    )
    position: Mapped[int] = mapped_column(SmallInteger)
    value: Mapped[str] = mapped_column(String(OPTION_VALUE_MAX))
    label: Mapped[str] = mapped_column(String(LABEL_MAX))
