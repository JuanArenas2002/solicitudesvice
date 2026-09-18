from enum import StrEnum


class RequestStatus(StrEnum):
    BORRADOR = "BORRADOR"
    ENVIADA = "ENVIADA"
    EN_REVISION = "EN_REVISION"
    CORRECCION_SOLICITADA = "CORRECCION_SOLICITADA"
    REENVIADA = "REENVIADA"
    APROBADA = "APROBADA"
    RECHAZADA = "RECHAZADA"

    @property
    def is_terminal(self) -> bool:
        return self in (RequestStatus.APROBADA, RequestStatus.RECHAZADA)
