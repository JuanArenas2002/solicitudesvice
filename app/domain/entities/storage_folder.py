import re
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.domain.entities.product_type import FOLDER_NAME_PATTERN
from app.domain.exceptions.errors import InvalidValue
from app.domain.value_objects.identifiers import CEDULA_PATTERN


@dataclass(frozen=True, slots=True)
class StorageFolder:
    """Carpeta de soportes de una solicitud:  <cédula>/<producto>/Solicitud <N>.

    N cuenta las solicitudes con soportes de esa persona para ese producto (1, 2, 3...). Se asigna
    la primera vez que se adjunta un archivo, cuando ya se conoce la cédula.
    """

    request_id: UUID
    cedula: str
    product_folder: str
    sequence: int
    created_at: datetime

    def __post_init__(self) -> None:
        if re.fullmatch(CEDULA_PATTERN, self.cedula) is None:
            raise InvalidValue("cedula inválida para la carpeta", field="cedula")
        if re.fullmatch(FOLDER_NAME_PATTERN, self.product_folder) is None:
            raise InvalidValue("nombre de carpeta del producto inválido", field="folder_name")
        if self.sequence < 1:
            raise InvalidValue("La secuencia de la carpeta debe ser >= 1", field="sequence")

    @property
    def relative_path(self) -> str:
        return f"{self.cedula}/{self.product_folder}/Solicitud {self.sequence}"
