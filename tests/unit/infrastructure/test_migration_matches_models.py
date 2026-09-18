"""Verifica, SIN base de datos, que la migración 0001 crea exactamente lo que declaran los modelos.

Compara tabla por tabla (columnas, tipos, defaults, CHECK, FK, UNIQUE) el DDL de PostgreSQL de
los modelos contra el SQL que Alembic genera en modo offline. La verificación real contra un
PostgreSQL (upgrade/downgrade/autogenerate) vive en tests/integration/.
"""

import re
from io import StringIO
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from app.infrastructure.database.catalog import lookup_rows
from app.infrastructure.database.models import Base

ROOT = Path(__file__).resolve().parents[3]
DIALECT = postgresql.dialect()
TABLE_RE = re.compile(r"CREATE TABLE (\w+) \(\n(.*?)\n\)", re.S)
INDEX_RE = re.compile(r"CREATE (?:UNIQUE )?INDEX [^;]+")


def _normalize(text: str) -> str:
    return " ".join(text.split())


def _table_lines(body: str) -> frozenset[str]:
    return frozenset(_normalize(line) for line in re.split(r",\s*\n", body) if line.strip())


def _migration_sql(direction: str) -> str:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "app/infrastructure/database/migrations"))
    config.set_main_option("sqlalchemy.url", "postgresql+psycopg://user:pass@localhost/db")
    config.output_buffer = StringIO()
    if direction == "up":
        command.upgrade(config, "head", sql=True)
    else:
        command.downgrade(config, "head:base", sql=True)
    return config.output_buffer.getvalue()


@pytest.fixture(scope="module")
def model_tables() -> dict[str, frozenset[str]]:
    return {
        t.name: _table_lines(TABLE_RE.search(str(CreateTable(t).compile(dialect=DIALECT))).group(2))  # type: ignore[union-attr]
        for t in Base.metadata.sorted_tables
    }


@pytest.fixture(scope="module")
def model_indexes() -> frozenset[str]:
    return frozenset(
        _normalize(str(CreateIndex(i).compile(dialect=DIALECT)))
        for t in Base.metadata.sorted_tables
        for i in t.indexes
    )


@pytest.fixture(scope="module")
def upgrade_sql() -> str:
    return _migration_sql("up")


def test_model_ddl_has_no_backslashes() -> None:
    """Con backslashes, el modo offline los duplica y el regex de PostgreSQL cambia de sentido."""
    for table in Base.metadata.sorted_tables:
        assert "\\" not in str(CreateTable(table).compile(dialect=DIALECT)), table.name


def test_expected_tables_exist(model_tables: dict[str, frozenset[str]]) -> None:
    assert set(model_tables) == {
        "users",
        "auth_sessions",
        "refresh_tokens",
        "research_product_requests",
        "request_answers",
        "request_corrections",
        "request_status_history",
        "request_attachments",
        "storage_counters",
        "storage_folders",
        "audit_logs",
        "request_counters",
        "product_types",
        "form_versions",
        "form_sections",
        "form_fields",
        "form_field_options",
        "form_field_document_types",
        "user_product_assignments",
        "notifications",
        # catalogos
        "roles",
        "request_statuses",
        "correction_statuses",
        "form_statuses",
        "value_kinds",
        "document_types",
        "field_types",
        "audit_categories",
        "audit_actions",
    }


def test_upgrade_creates_the_same_tables(
    upgrade_sql: str, model_tables: dict[str, frozenset[str]]
) -> None:
    created = {
        name: _table_lines(body)
        for name, body in TABLE_RE.findall(upgrade_sql)
        if name != "alembic_version"
    }
    assert set(created) == set(model_tables)
    for name, expected in model_tables.items():
        assert created[name] == expected, (
            f"{name}: sólo en modelo={sorted(expected - created[name])} "
            f"sólo en migración={sorted(created[name] - expected)}"
        )


def test_upgrade_creates_the_same_indexes(upgrade_sql: str, model_indexes: frozenset[str]) -> None:
    created = frozenset(_normalize(m) for m in INDEX_RE.findall(upgrade_sql))
    assert created == model_indexes, (
        f"sólo en modelo={sorted(model_indexes - created)} "
        f"sólo en migración={sorted(created - model_indexes)}"
    )


def test_downgrade_drops_every_table_in_fk_safe_order() -> None:
    dropped = [t for t in re.findall(r"DROP TABLE (\w+)", _migration_sql("down"))]
    assert set(dropped) == set(Base.metadata.tables)
    position = {name: i for i, name in enumerate(dropped)}
    for table in Base.metadata.tables.values():
        for fk in table.foreign_keys:
            referenced = fk.column.table.name
            if referenced != table.name:
                # La tabla que referencia debe borrarse antes que la referenciada.
                assert position[table.name] < position[referenced], (table.name, referenced)


def _seeded_rows(sql: str) -> dict[str, list[tuple[object, ...]]]:
    rows: dict[str, list[tuple[object, ...]]] = {}
    for table, values in re.findall(r"INSERT INTO (\w+) \([^)]*\) VALUES \((.*)\);", sql):
        parsed = tuple(
            int(v) if v.strip().isdigit() else v.strip().strip("'") for v in values.split(", ")
        )
        rows.setdefault(table, []).append(parsed)
    return rows


def test_seeded_lookup_tables_match_the_catalog(upgrade_sql: str) -> None:
    """La semilla de la migración (ids fijos) debe coincidir con catalog.py y con el dominio."""
    seeded = _seeded_rows(upgrade_sql)
    for table, expected in lookup_rows().items():
        assert sorted(seeded[table], key=str) == sorted(expected, key=str), table
