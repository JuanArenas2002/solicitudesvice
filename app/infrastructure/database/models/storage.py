import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, UniqueConstraint, Uuid, column
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.value_objects.identifiers import CEDULA_PATTERN
from app.infrastructure.database.base import Base, timestamptz


class StorageCounterModel(Base):
    """Contador por (cédula, producto) para numerar 'Solicitud 1, 2, 3...' sin repetir."""

    __tablename__ = "storage_counters"
    __table_args__ = (
        CheckConstraint(column("cedula").regexp_match(CEDULA_PATTERN), name="cedula_format"),
        CheckConstraint(column("last_value") >= 0, name="last_value_non_negative"),
    )

    cedula: Mapped[str] = mapped_column(String(15), primary_key=True)
    product_type_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("product_types.id", ondelete="RESTRICT"), primary_key=True
    )
    last_value: Mapped[int] = mapped_column(Integer)


class StorageFolderModel(Base):
    """Carpeta de soportes de una solicitud: <cédula>/<producto>/Solicitud <N>."""

    __tablename__ = "storage_folders"
    __table_args__ = (
        CheckConstraint(column("cedula").regexp_match(CEDULA_PATTERN), name="cedula_format"),
        CheckConstraint(column("sequence") >= 1, name="sequence_positive"),
        UniqueConstraint(
            "cedula", "product_type_id", "sequence", name="uq_storage_folders_cedula_type_sequence"
        ),
    )

    request_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("research_product_requests.id", ondelete="RESTRICT"), primary_key=True
    )
    cedula: Mapped[str] = mapped_column(String(15))
    product_type_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("product_types.id", ondelete="RESTRICT")
    )
    sequence: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = timestamptz(server_now=True)
