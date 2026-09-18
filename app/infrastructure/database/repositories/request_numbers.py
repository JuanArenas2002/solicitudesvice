from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.value_objects.request_number import RequestNumber
from app.infrastructure.database.models.request_counter import RequestCounterModel


class SqlAlchemyRequestNumberGenerator:
    """Contador anual con lock de fila (SELECT ... FOR UPDATE).

    Dos transacciones concurrentes se serializan sobre la fila del año: nunca repiten número y,
    como el incremento se confirma con la transacción, tampoco quedan huecos por rollbacks.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def next(self, year: int) -> RequestNumber:
        counter = self._locked(year)
        if counter is None:
            # Primer número del año: si otra transacción lo crea a la vez, gana una y la otra relee.
            try:
                with self._session.begin_nested():
                    self._session.add(RequestCounterModel(year=year, last_value=0))
            except IntegrityError:
                pass
            counter = self._locked(year)
        if counter is None:  # pragma: no cover - solo si la fila desaparece entre operaciones
            raise RuntimeError(f"No se pudo obtener el contador del año {year}")
        counter.last_value += 1
        number = RequestNumber(year, counter.last_value)  # valida el rango antes de confirmar
        self._session.flush()
        return number

    def _locked(self, year: int) -> RequestCounterModel | None:
        return self._session.scalars(
            select(RequestCounterModel)
            .where(RequestCounterModel.year == year)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).one_or_none()
