import os

import pytest
from dotenv import dotenv_values

# TEST_DATABASE_URL puede venir del entorno o del .env local (que no se versiona).
if "TEST_DATABASE_URL" not in os.environ:
    _url = dotenv_values(".env").get("TEST_DATABASE_URL")
    if _url:
        os.environ["TEST_DATABASE_URL"] = _url


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Los tests de integración exigen un PostgreSQL real; sin él se SALTAN explícitamente."""
    if os.environ.get("TEST_DATABASE_URL"):
        return
    skip = pytest.mark.skip(reason="TEST_DATABASE_URL no definida: requiere un PostgreSQL real")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)
