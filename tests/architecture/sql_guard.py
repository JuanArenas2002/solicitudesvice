"""Detector estático de SQL manual (regla absoluta: toda persistencia pasa por el ORM).

Analiza el AST, sin excepciones ni listas de permitidos. Detecta:
  * text(), literal_column(), DDL(), TextClause, exec_driver_sql() y sus imports
  * strings / f-strings / + / % / .format enviados a execute(), exec(), scalar(), scalars()
  * op.execute() (Alembic) en cualquier forma
  * CheckConstraint("..."), Computed("...") o postgresql_where="..." con SQL en texto
  * cualquier literal de texto que tenga forma de sentencia SQL
Las construcciones ORM/Core (select(), update(), column(), func, and_/or_) están permitidas.
"""

import ast
import re

FORBIDDEN_IMPORTS = {"text", "literal_column", "DDL", "TextClause"}
FORBIDDEN_ATTRIBUTES = {"exec_driver_sql", "literal_column", "DDL", "TextClause"}
EXECUTE_METHODS = {"execute", "exec", "executemany", "scalar", "scalars", "exec_driver_sql"}
SQL_STRING_CONSTRUCTS = {"CheckConstraint", "Computed"}
SQL_STRING_KWARGS = {"sqltext", "postgresql_where", "sqlite_where", "whereclause"}
SQLALCHEMY_ALIASES = {"sa", "sqlalchemy", "sql"}

_SQL_LIKE = re.compile(
    r"^\s*(select\s.+\sfrom\s|insert\s+into\s|update\s+\w+\s+set\s|delete\s+from\s"
    r"|create\s+(unique\s+)?(table|index|view|function|trigger|extension)\s"
    r"|alter\s+table\s|drop\s+(table|index|view)\s|truncate\s)",
    re.IGNORECASE | re.DOTALL,
)


def _is_stringish(node: ast.expr) -> bool:
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str)
    if isinstance(node, ast.JoinedStr):
        return True
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add | ast.Mod):
        return _is_stringish(node.left) or _is_stringish(node.right)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        return node.func.attr == "format" and _is_stringish(node.func.value)
    return False


def _root_name(node: ast.expr) -> str | None:
    while isinstance(node, ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def _docstring_nodes(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                ids.add(id(first.value))
    return ids


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    if isinstance(node.func, ast.Name):
        return node.func.id
    return None


def find_violations(source: str, filename: str = "<memory>") -> list[str]:
    tree = ast.parse(source, filename)
    docstrings = _docstring_nodes(tree)
    found: list[str] = []

    def flag(node: ast.AST, message: str) -> None:
        found.append(f"{filename}:{getattr(node, 'lineno', 0)}: {message}")

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "sqlalchemy":
            for alias in node.names:
                if alias.name in FORBIDDEN_IMPORTS:
                    flag(node, f"importa {alias.name} de sqlalchemy (SQL textual)")
        elif isinstance(node, ast.Attribute):
            if node.attr in FORBIDDEN_ATTRIBUTES:
                flag(node, f"uso de .{node.attr} (SQL textual)")
            elif node.attr == "text" and _root_name(node.value) in SQLALCHEMY_ALIASES:
                flag(node, "uso de sqlalchemy.text (SQL textual)")
        elif isinstance(node, ast.Call):
            name = _call_name(node)
            first = node.args[0] if node.args else None
            if (
                name == "execute"
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "op"
            ):
                flag(node, "op.execute() prohibido: usar operaciones de Alembic")
            elif name in EXECUTE_METHODS and first is not None and _is_stringish(first):
                flag(node, f"string SQL enviado a {name}()")
            if name in SQL_STRING_CONSTRUCTS and first is not None and _is_stringish(first):
                flag(node, f"{name} con SQL en texto: usar expresiones SQLAlchemy")
            for keyword in node.keywords:
                if keyword.arg in SQL_STRING_KWARGS and _is_stringish(keyword.value):
                    flag(node, f"{keyword.arg} con SQL en texto: usar expresiones SQLAlchemy")
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
            and _SQL_LIKE.match(node.value)
        ):
            flag(node, "literal con forma de sentencia SQL")
    return found
