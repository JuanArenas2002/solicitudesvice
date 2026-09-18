import hashlib
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.domain.entities.product_type import ProductType, default_folder_name
from app.domain.entities.storage_folder import StorageFolder
from app.domain.exceptions.errors import FileTooLarge, InvalidValue
from app.domain.services.attachment_rules import (
    ALLOWED,
    MAX_FILE_NAME,
    sanitize_file_name,
    unique_file_name,
    validate_upload,
)

NOW = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)
PDF = b"%PDF-1.7\n%contenido"
MAX = 1024 * 1024


# ---------------- nombres de archivo ----------------
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("soporte.pdf", "soporte.pdf"),
        ("  Mi   soporte  final .PDF ", "Mi soporte final.PDF"),
        ("../../etc/passwd.pdf", "passwd.pdf"),  # sin rutas
        ("C:\\Users\\Ana\\carta.pdf", "carta.pdf"),
        ('a<b>c:"d"|e?f*.pdf', "a_b_c__d__e_f_.pdf"),  # caracteres prohibidos en Windows
        ("informe\x00.pdf", "informe_.pdf"),  # byte nulo
        ("con.pdf", "_con.pdf"),  # nombre reservado de Windows
        ("LPT1.docx", "_LPT1.docx"),
        ("nombre.con.puntos.pdf", "nombre.con.puntos.pdf"),
        ("trailing. .pdf", "trailing.pdf"),
    ],
)
def test_file_names_are_made_safe(raw: str, expected: str) -> None:
    assert sanitize_file_name(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "sinextension", ".pdf", "..", "/", "carpeta/"])
def test_names_without_a_usable_name_are_rejected(raw: str) -> None:
    with pytest.raises(InvalidValue):
        sanitize_file_name(raw)


def test_very_long_names_keep_their_extension() -> None:
    name = sanitize_file_name("x" * 500 + ".pdf")
    assert len(name) <= MAX_FILE_NAME and name.endswith(".pdf")


def test_unique_names_ignore_case_like_windows() -> None:
    assert unique_file_name("a.pdf", []) == "a.pdf"
    assert unique_file_name("a.pdf", ["A.PDF"]) == "a (2).pdf"
    assert unique_file_name("a.pdf", ["a.pdf", "a (2).pdf", "A (3).PDF"]) == "a (4).pdf"
    assert unique_file_name("b.pdf", ["a.pdf"]) == "b.pdf"


# ---------------- contenido ----------------
def test_valid_upload_is_described_with_its_hash() -> None:
    result = validate_upload("Soporte.PDF", PDF, MAX)
    assert (result.file_name, result.mime_type, result.size) == (
        "Soporte.PDF",
        "application/pdf",
        len(PDF),
    )
    assert result.sha256 == hashlib.sha256(PDF).hexdigest()


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("a.pdf", b"%PDF-1.4"),
        ("a.png", b"\x89PNG\r\n\x1a\n" + b"\0" * 8),
        ("a.jpg", b"\xff\xd8\xff\xe0" + b"\0" * 8),
        ("a.jpeg", b"\xff\xd8\xff\xdb"),
        ("a.zip", b"PK\x03\x04rest"),
        ("a.docx", b"PK\x03\x04rest"),
        ("a.xlsx", b"PK\x03\x04rest"),
        ("a.pptx", b"PK\x03\x04rest"),
        ("a.doc", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1rest"),
        ("a.xls", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1rest"),
        ("a.ppt", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1rest"),
    ],
)
def test_every_allowed_type_is_accepted_with_its_signature(name: str, content: bytes) -> None:
    assert validate_upload(name, content, MAX).mime_type == ALLOWED[name.rpartition(".")[2]][0]


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("virus.exe", b"MZ\x90\x00"),  # extensión no permitida
        ("script.js", b"alert(1)"),
        ("pagina.html", b"<html>"),
        ("falso.pdf", b"<html><script>"),  # extensión válida, contenido que no corresponde
        ("falso.png", PDF),
        ("falso.docx", PDF),
        ("doble.pdf.exe", b"MZ"),
        ("vacio.pdf", b""),
    ],
)
def test_files_that_are_not_what_they_claim_are_rejected(name: str, content: bytes) -> None:
    with pytest.raises(InvalidValue):
        validate_upload(name, content, MAX)


def test_size_limit_is_enforced() -> None:
    validate_upload("a.pdf", PDF, len(PDF))  # justo en el límite
    with pytest.raises(FileTooLarge):
        validate_upload("a.pdf", PDF, len(PDF) - 1)
    assert issubclass(FileTooLarge, InvalidValue)


# ---------------- carpeta ----------------
def test_storage_folder_builds_the_documented_path() -> None:
    folder = StorageFolder(uuid4(), "1003895357", "Articulos", 2, NOW)
    assert folder.relative_path == "1003895357/Articulos/Solicitud 2"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"cedula": "12"},
        {"cedula": "../123456"},
        {"cedula": "12345abc"},
        {"product_folder": "../Articulos"},
        {"product_folder": "Con Espacio"},
        {"product_folder": "a/b"},
        {"product_folder": ""},
        {"sequence": 0},
    ],
)
def test_storage_folder_rejects_unsafe_parts(kwargs: dict[str, object]) -> None:
    data: dict[str, object] = {
        "request_id": uuid4(),
        "cedula": "1003895357",
        "product_folder": "Articulos",
        "sequence": 1,
        "created_at": NOW,
    }
    with pytest.raises(InvalidValue):
        StorageFolder(**{**data, **kwargs})  # type: ignore[arg-type]


# ---------------- carpeta del producto ----------------
def test_product_folder_defaults_to_a_safe_version_of_the_name() -> None:
    assert default_folder_name("Artículo científico") == "Articulo_cientifico"
    assert default_folder_name("  Desarrollo Tecnológico (DT)  ") == "Desarrollo_Tecnologico_DT"
    assert ProductType.create("DT", "Desarrollo Tecnológico", None, NOW).folder_name == (
        "Desarrollo_Tecnologico"
    )


def test_product_folder_can_be_chosen_explicitly_and_is_validated() -> None:
    assert ProductType.create("DT", "Desarrollo", None, NOW, " DT ").folder_name == "DT"
    for bad in ("../DT", "con espacio", "a.b", "a/b", "x" * 51, "_empieza"):
        with pytest.raises(InvalidValue) as error:
            ProductType.create("DT", "Desarrollo", None, NOW, bad)
        assert error.value.field == "folder_name"
    with pytest.raises(InvalidValue):  # el nombre no deja ningún carácter utilizable
        ProductType.create("DT", "日本語", None, NOW)


def test_product_folder_does_not_change_on_update() -> None:
    product = ProductType.create("DT", "Desarrollo", None, NOW, "DT")
    product.update(NOW, name="Otro nombre", is_active=False)
    assert product.folder_name == "DT"
