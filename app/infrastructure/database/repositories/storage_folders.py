from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.entities.storage_folder import StorageFolder
from app.infrastructure.database.models.product_type import ProductTypeModel
from app.infrastructure.database.models.storage import StorageCounterModel, StorageFolderModel


class SqlAlchemyStorageFolderRepository:
    """Numeración de 'Solicitud N' por (cédula, producto) con lock de fila.

    Misma técnica que el número de solicitud: dos cargas simultáneas se serializan sobre la fila
    del contador, así que nunca reciben el mismo N ni dejan huecos por rollbacks.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, request_id: UUID) -> StorageFolder | None:
        row = self._session.execute(
            select(StorageFolderModel, ProductTypeModel.folder_name)
            .join(ProductTypeModel, ProductTypeModel.id == StorageFolderModel.product_type_id)
            .where(StorageFolderModel.request_id == request_id)
        ).one_or_none()
        if row is None:
            return None
        model, product_folder = row
        return StorageFolder(
            request_id=model.request_id,
            cedula=model.cedula,
            product_folder=product_folder,
            sequence=model.sequence,
            created_at=model.created_at,
        )

    def create(
        self,
        request_id: UUID,
        cedula: str,
        product_type_id: int,
        product_folder: str,
        now: datetime,
    ) -> StorageFolder:
        counter = self._locked(cedula, product_type_id)
        if counter is None:
            try:  # primera carpeta de esa cédula y producto: si otro la crea a la vez, se relee
                with self._session.begin_nested():
                    self._session.add(
                        StorageCounterModel(
                            cedula=cedula, product_type_id=product_type_id, last_value=0
                        )
                    )
            except IntegrityError:
                pass
            counter = self._locked(cedula, product_type_id)
        if counter is None:  # pragma: no cover - solo si la fila desaparece entre operaciones
            raise RuntimeError("No se pudo obtener el contador de carpetas")
        counter.last_value += 1
        folder = StorageFolder(request_id, cedula, product_folder, counter.last_value, now)
        self._session.add(
            StorageFolderModel(
                request_id=request_id,
                cedula=cedula,
                product_type_id=product_type_id,
                sequence=folder.sequence,
                created_at=now,
            )
        )
        self._session.flush()
        return folder

    def _locked(self, cedula: str, product_type_id: int) -> StorageCounterModel | None:
        return self._session.scalars(
            select(StorageCounterModel)
            .where(
                StorageCounterModel.cedula == cedula,
                StorageCounterModel.product_type_id == product_type_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        ).one_or_none()
