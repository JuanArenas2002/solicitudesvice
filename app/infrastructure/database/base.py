from datetime import datetime

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, MappedColumn, mapped_column

# Nombres deterministas: la migración y los modelos deben producir exactamente los mismos.
# Los CHECK reciben prefijo automático (ck_<tabla>_<nombre>); el resto se nombra explícitamente.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def timestamptz(*, server_now: bool = False) -> MappedColumn[datetime]:
    """Columna timestamptz (UTC). La nulabilidad la define la anotación Mapped[...]."""
    return mapped_column(DateTime(timezone=True), server_default=func.now() if server_now else None)
