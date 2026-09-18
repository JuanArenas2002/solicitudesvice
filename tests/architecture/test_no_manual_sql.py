from pathlib import Path

import pytest

from tests.architecture.sql_guard import find_violations

APP_DIR = Path(__file__).resolve().parents[2] / "app"

BAD_SNIPPETS = [
    "from sqlalchemy import text\nsession.execute(text('select 1'))",
    "from sqlalchemy.sql import text as t\nt('x')",
    "from sqlalchemy import literal_column\n",
    "import sqlalchemy as sa\nsa.text('x')",
    "conn.exec_driver_sql('select 1')",
    "session.execute('SELECT 1')",
    "session.execute(f'SELECT {x}')",
    "session.execute('select ' + col)",
    "session.execute('select %s' % col)",
    "session.execute('select {}'.format(col))",
    "session.scalars('select 1')",
    "op.execute('ALTER TABLE t ADD c int')",
    "op.execute(stmt)",
    "sa.CheckConstraint('a > 0')",
    "CheckConstraint(sqltext='a > 0', name='x')",
    "Index('i', 'c', postgresql_where='a > 0')",
    "query = 'SELECT id FROM users WHERE id = 1'",
    "sql = 'DELETE FROM users'",
]

GOOD_SNIPPETS = [
    "session.scalars(select(User).where(User.id == 1))",
    "session.get(User, 1)",
    "session.execute(select(User))",
    "CheckConstraint(column('a') > 0, name='x')",
    "Index('i', 'c', postgresql_where=column('a') == 'X')",
    "label = 'select an option'",
    "def f():\n    '''SELECT id FROM users (ejemplo en docstring)'''\n",
    "op.create_table('t', sa.Column('a', sa.Integer()))",
]


@pytest.mark.parametrize("source", BAD_SNIPPETS)
def test_guard_detects_manual_sql(source: str) -> None:
    assert find_violations(source), f"El guard no detectó: {source!r}"


@pytest.mark.parametrize("source", GOOD_SNIPPETS)
def test_guard_allows_orm_constructs(source: str) -> None:
    assert find_violations(source) == []


def test_application_contains_no_manual_sql() -> None:
    """Regla absoluta: sin SQL manual en app/ (migraciones incluidas). Sin excepciones."""
    files = sorted(APP_DIR.rglob("*.py"))
    assert files, "No se encontraron archivos en app/"
    violations = [v for f in files for v in find_violations(f.read_text("utf-8"), str(f))]
    assert violations == [], "\n".join(violations)
