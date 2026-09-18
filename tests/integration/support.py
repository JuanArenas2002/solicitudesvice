import os
from pathlib import Path

from alembic.config import Config

ROOT = Path(__file__).resolve().parents[2]


def alembic_config(url: str | None = None) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "app/infrastructure/database/migrations"))
    config.set_main_option(
        "sqlalchemy.url", (url or os.environ["TEST_DATABASE_URL"]).replace("%", "%%")
    )
    return config
