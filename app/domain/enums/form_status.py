from enum import StrEnum


class FormStatus(StrEnum):
    BORRADOR = "BORRADOR"  # editable
    PUBLICADA = "PUBLICADA"  # inmutable; la que usan las solicitudes nuevas (una por producto)
    RETIRADA = "RETIRADA"  # reemplazada; sigue sirviendo a las solicitudes que ya la usaban
