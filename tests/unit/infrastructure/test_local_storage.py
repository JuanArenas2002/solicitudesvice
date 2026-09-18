from pathlib import Path

import pytest

from app.infrastructure.storage.local import LocalFileStorage

KEY = "1003895357/Articulos/Solicitud 1/soporte.pdf"


@pytest.fixture
def storage(tmp_path: Path) -> LocalFileStorage:
    return LocalFileStorage(tmp_path / "storage")


def test_files_are_stored_in_the_documented_tree(storage: LocalFileStorage, tmp_path: Path) -> None:
    storage.save(KEY, b"%PDF-contenido")
    assert (
        tmp_path / "storage" / "1003895357" / "Articulos" / "Solicitud 1" / "soporte.pdf"
    ).read_bytes() == b"%PDF-contenido"
    assert b"".join(storage.open(KEY)) == b"%PDF-contenido"


def test_saving_replaces_atomically_and_leaves_no_temporary_files(
    storage: LocalFileStorage, tmp_path: Path
) -> None:
    storage.save(KEY, b"uno")
    storage.save(KEY, b"dos")
    assert b"".join(storage.open(KEY)) == b"dos"
    leftovers = [p.name for p in (tmp_path / "storage").rglob("*") if p.name.startswith(".tmp-")]
    assert leftovers == []


def test_large_files_are_streamed_in_chunks(storage: LocalFileStorage) -> None:
    content = b"x" * (200 * 1024)
    storage.save(KEY, content)
    chunks = list(storage.open(KEY))
    assert len(chunks) > 1 and b"".join(chunks) == content


def test_missing_files_and_idempotent_delete(storage: LocalFileStorage) -> None:
    with pytest.raises(FileNotFoundError):
        storage.open(KEY)
    storage.delete(KEY)  # no falla si no existe
    storage.save(KEY, b"x")
    storage.delete(KEY)
    with pytest.raises(FileNotFoundError):
        storage.open(KEY)


@pytest.mark.parametrize(
    "key",
    [
        "",
        "../fuera.pdf",
        "a/../../fuera.pdf",
        "/etc/passwd",
        "a//b.pdf",
        "a/./b.pdf",
        "a\\b.pdf",
        "C:/Windows/x.pdf",
        "a/..",
        "1003895357/../../secreto.pdf",
    ],
)
def test_path_traversal_is_impossible(storage: LocalFileStorage, tmp_path: Path, key: str) -> None:
    with pytest.raises(ValueError):
        storage.save(key, b"x")
    with pytest.raises(ValueError):
        storage.delete(key)
    assert not (tmp_path / "fuera.pdf").exists()


def test_a_symlink_cannot_escape_the_root(storage: LocalFileStorage, tmp_path: Path) -> None:
    outside = tmp_path / "afuera"
    outside.mkdir()
    link = tmp_path / "storage" / "enlace"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Sin permiso para crear enlaces simbólicos en este sistema")
    with pytest.raises(ValueError):
        storage.save("enlace/robado.pdf", b"x")
    assert list(outside.iterdir()) == []
