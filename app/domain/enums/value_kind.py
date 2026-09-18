from enum import StrEnum


class ValueKind(StrEnum):
    """En qué columna tipada de request_answers se guarda la respuesta de un campo."""

    TEXT = "TEXT"
    NUMBER = "NUMBER"
    DATE = "DATE"
    BOOLEAN = "BOOLEAN"
    OPTION = "OPTION"
    FILE = "FILE"  # los campos de soporte no guardan respuesta: su valor son archivos adjuntos
