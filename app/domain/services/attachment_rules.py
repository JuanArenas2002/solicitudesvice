"""Reglas de los soportes: qué archivos se aceptan, cómo se nombran y cómo se verifican.

Un archivo se acepta solo si su extensión está permitida Y su contenido empieza con la firma que le
corresponde (no se confía en la extensión ni en el tipo declarado por el cliente).
"""

import hashlib
import re
import unicodedata
from collections.abc import Collection
from dataclasses import dataclass

from app.domain.exceptions.errors import FileTooLarge, InvalidValue

MAX_FILE_NAME = 120
MAX_FILES_PER_REQUEST = 30

_ZIP = (b"PK\x03\x04", b"PK\x05\x06")
_OLE = (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",)
OFFICE_XML = "application/vnd.openxmlformats-officedocument"

# extensión -> (tipo MIME, firmas válidas al inicio del archivo)
ALLOWED: dict[str, tuple[str, tuple[bytes, ...]]] = {
    "pdf": ("application/pdf", (b"%PDF-",)),
    "png": ("image/png", (b"\x89PNG\r\n\x1a\n",)),
    "jpg": ("image/jpeg", (b"\xff\xd8\xff",)),
    "jpeg": ("image/jpeg", (b"\xff\xd8\xff",)),
    "zip": ("application/zip", _ZIP),
    "docx": (f"{OFFICE_XML}.wordprocessingml.document", _ZIP),
    "xlsx": (f"{OFFICE_XML}.spreadsheetml.sheet", _ZIP),
    "pptx": (f"{OFFICE_XML}.presentationml.presentation", _ZIP),
    "doc": ("application/msword", _OLE),
    "xls": ("application/vnd.ms-excel", _OLE),
    "ppt": ("application/vnd.ms-powerpoint", _OLE),
}

_FORBIDDEN_CHARS = re.compile(r'[<>:"|?*\x00-\x1f]')
_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


@dataclass(frozen=True, slots=True)
class ValidatedFile:
    file_name: str
    mime_type: str
    size: int
    sha256: str


def sanitize_file_name(raw: str) -> str:
    """Nombre seguro para cualquier sistema de archivos (sin rutas, sin caracteres prohibidos)."""
    name = unicodedata.normalize("NFKC", raw).replace("\\", "/").split("/")[-1]
    name = " ".join(_FORBIDDEN_CHARS.sub("_", name).split()).strip(". ")
    if not name or "." not in name:
        raise InvalidValue("El archivo necesita un nombre con extensión", field="file")
    stem, _, extension = name.rpartition(".")
    if stem.upper() in _RESERVED:
        stem = f"_{stem}"
    stem = stem[: MAX_FILE_NAME - len(extension) - 1].rstrip(". ") or "archivo"
    return f"{stem}.{extension}"


def validate_upload(raw_name: str, content: bytes, max_bytes: int) -> ValidatedFile:
    name = sanitize_file_name(raw_name)
    extension = name.rpartition(".")[2].lower()
    allowed = ALLOWED.get(extension)
    if allowed is None:
        raise InvalidValue(
            f"Tipo no permitido (.{extension}). Permitidos: {', '.join(sorted(ALLOWED))}",
            field="file",
        )
    if not content:
        raise InvalidValue("El archivo está vacío", field="file")
    if len(content) > max_bytes:
        raise FileTooLarge(f"El archivo supera el máximo de {max_bytes // (1024 * 1024)} MB")
    mime_type, signatures = allowed
    if not content.startswith(signatures):
        raise InvalidValue(f"El contenido no corresponde a un archivo .{extension}", field="file")
    return ValidatedFile(name, mime_type, len(content), hashlib.sha256(content).hexdigest())


def unique_file_name(name: str, taken: Collection[str]) -> str:
    """Si ya existe (sin distinguir mayúsculas, como Windows) agrega ' (2)', ' (3)'..."""
    used = {t.lower() for t in taken}
    if name.lower() not in used:
        return name
    stem, _, extension = name.rpartition(".")
    counter = 2
    while f"{stem} ({counter}).{extension}".lower() in used:
        counter += 1
    return f"{stem} ({counter}).{extension}"
