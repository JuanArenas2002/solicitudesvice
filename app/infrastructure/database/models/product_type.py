from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Identity,
    Index,
    Integer,
    String,
    column,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.entities.product_type import (
    CODE_PATTERN,
    DESCRIPTION_MAX,
    FOLDER_NAME_PATTERN,
    NAME_MAX,
)
from app.infrastructure.database.base import Base, timestamptz


class ProductTypeModel(Base):
    """Tipo de producto de investigación: un dato que gestionan los administradores."""

    __tablename__ = "product_types"
    __table_args__ = (
        CheckConstraint(column("code").regexp_match(CODE_PATTERN), name="code_format"),
        CheckConstraint(func.length(func.trim(column("name"))) > 0, name="name_not_blank"),
        CheckConstraint(
            column("folder_name").regexp_match(FOLDER_NAME_PATTERN), name="folder_name_format"
        ),
        # Sin distinguir mayúsculas: en Windows 'Articulos' y 'articulos' serían la misma carpeta.
        Index("uq_product_types_folder_lower", func.lower(column("folder_name")), unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(always=True), primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(NAME_MAX))
    description: Mapped[str | None] = mapped_column(String(DESCRIPTION_MAX))
    folder_name: Mapped[str] = mapped_column(String(50))  # carpeta de soportes; inmutable
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=true())
    created_at: Mapped[datetime] = timestamptz(server_now=True)
    updated_at: Mapped[datetime] = timestamptz(server_now=True)
