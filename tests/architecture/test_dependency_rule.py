import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "app"
STDLIB = set(sys.stdlib_module_names)
FRAMEWORKS = (
    "fastapi",
    "starlette",
    "sqlalchemy",
    "alembic",
    "psycopg",
    "pydantic",
    "jwt",
    "argon2",
)


def _imports(path: Path) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text("utf-8"))):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, f"{path}: imports relativos prohibidos"
            modules.add(node.module or "")
    return modules


def _top(module: str) -> str:
    return module.split(".")[0]


def _under(module: str, *prefixes: str) -> bool:
    return any(module == p or module.startswith(p + ".") for p in prefixes)


def bad_imports(layer: str, modules: set[str]) -> list[str]:
    """Imports que la capa `layer` no puede tener (regla de dependencias)."""
    bad: list[str] = []
    for m in modules:
        if layer == "domain":
            # El dominio solo conoce la stdlib y a sí mismo.
            ok = _top(m) in STDLIB or _under(m, "app.domain")
        elif layer == "application":
            ok = _top(m) in STDLIB or _under(m, "app.domain", "app.application")
        elif layer == "infrastructure":
            ok = not _under(m, "app.interfaces", "fastapi", "starlette")
        elif layer == "interfaces":
            ok = not _under(m, "sqlalchemy", "alembic", "psycopg")
        elif layer == "interfaces/routes":
            ok = not _under(m, "sqlalchemy", "alembic", "psycopg", "app.infrastructure")
        else:
            raise AssertionError(layer)
        if not ok:
            bad.append(m)
    return sorted(bad)


LAYERS = {
    "domain": APP / "domain",
    "application": APP / "application",
    "infrastructure": APP / "infrastructure",
    "interfaces": APP / "interfaces",
    "interfaces/routes": APP / "interfaces" / "api" / "routes",
}


@pytest.mark.parametrize("layer", list(LAYERS))
def test_layer_respects_dependency_rule(layer: str) -> None:
    violations = [
        f"{path.relative_to(ROOT)} importa {module}"
        for path in sorted(LAYERS[layer].rglob("*.py"))
        for module in bad_imports(layer, _imports(path))
    ]
    assert violations == [], "\n".join(violations)


def test_domain_is_not_empty() -> None:
    assert list(LAYERS["domain"].rglob("*.py")), "El test sería vacuo: no hay archivos de dominio"


def test_dependency_checker_detects_violations() -> None:
    assert bad_imports("domain", {"sqlalchemy.orm", "pydantic", "app.infrastructure.x"})
    assert bad_imports("domain", {"dataclasses", "app.domain.enums.role", "uuid"}) == []
    assert bad_imports("application", {"fastapi", "app.infrastructure.database"})
    assert bad_imports("application", {"app.domain.entities.user", "typing"}) == []
    assert bad_imports("infrastructure", {"app.interfaces.api"})
    assert bad_imports("interfaces/routes", {"app.infrastructure.database.session"})
    assert bad_imports("interfaces", {"sqlalchemy.orm"})


def test_production_code_never_imports_tests() -> None:
    for path in APP.rglob("*.py"):
        assert not any(_under(m, "tests") for m in _imports(path)), path
