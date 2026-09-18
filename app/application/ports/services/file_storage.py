from collections.abc import Iterator
from typing import Protocol


class FileStorage(Protocol):
    """Almacén de archivos. Hoy disco local; mañana S3, MinIO o Azure Blob sin tocar el dominio.

    `key` es una ruta relativa con '/' (p. ej. 1003895357/Articulos/Solicitud 1/soporte.pdf).
    """

    def save(self, key: str, content: bytes) -> None:
        """Escribe el archivo de forma atómica (sin dejar archivos a medias)."""
        ...

    def open(self, key: str) -> Iterator[bytes]:
        """Devuelve el contenido en bloques. Lanza FileNotFoundError si no existe."""
        ...

    def delete(self, key: str) -> None:
        """Borra el archivo; no falla si ya no existe."""
        ...
