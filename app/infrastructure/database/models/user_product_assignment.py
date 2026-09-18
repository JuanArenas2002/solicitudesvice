import uuid

from sqlalchemy import ForeignKey, Index, Integer, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class UserProductAssignmentModel(Base):
    """Productos que revisa cada usuario administrativo (el rol lo valida el caso de uso)."""

    __tablename__ = "user_product_assignments"
    __table_args__ = (Index("ix_user_product_assignments_product", "product_type_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    product_type_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("product_types.id", ondelete="RESTRICT"), primary_key=True
    )
