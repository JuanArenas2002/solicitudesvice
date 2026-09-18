from sqlalchemy import CheckConstraint, Integer, SmallInteger, column
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.value_objects.request_number import MAX_SEQUENCE
from app.infrastructure.database.base import Base


class RequestCounterModel(Base):
    """Contador anual de SOL-AAAA-NNNNNN; se incrementa con lock de fila en la transacción."""

    __tablename__ = "request_counters"
    __table_args__ = (
        CheckConstraint(column("last_value").between(0, MAX_SEQUENCE), name="last_value_range"),
    )

    year: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False)
    last_value: Mapped[int] = mapped_column(Integer)
