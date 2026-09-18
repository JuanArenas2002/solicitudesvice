import os
from collections.abc import Iterator

import pytest
from alembic import command
from sqlalchemy import Engine, create_engine, delete
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.database.models import Base
from app.infrastructure.database.session import create_session_factory
from tests.integration.support import alembic_config

CATALOG_TABLES = {  # catalogos fijos sembrados por la migracion (no se limpian entre tests)
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


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    """Migra una base de datos VACÍA (TEST_DATABASE_URL) a `head` y la deja vacía al terminar."""
    url = os.environ["TEST_DATABASE_URL"]
    config = alembic_config(url)
    command.upgrade(config, "head")
    eng = create_engine(url)
    yield eng
    eng.dispose()
    command.downgrade(config, "base")


@pytest.fixture(autouse=True)
def clean_tables(engine: Engine) -> None:
    """Cada test parte sin datos (los catálogos sembrados se conservan)."""
    with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            if table.name not in CATALOG_TABLES:
                connection.execute(delete(table))


@pytest.fixture
def session_factory(engine: Engine) -> sessionmaker[Session]:
    return create_session_factory(engine)
