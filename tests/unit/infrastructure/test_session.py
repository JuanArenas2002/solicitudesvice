from pydantic import SecretStr

from app.config.settings import Settings
from app.infrastructure.database.session import create_db_engine, create_session_factory


def test_engine_uses_configured_pool_and_session_factory_keeps_objects_after_commit() -> None:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        database_url="postgresql+psycopg://u:p@localhost/db",
        jwt_secret_key=SecretStr("s" * 32),
        db_pool_size=7,
        db_max_overflow=3,
    )
    engine = create_db_engine(settings)  # no se conecta hasta la primera consulta
    assert engine.pool.size() == 7  # type: ignore[attr-defined]
    assert engine.pool._max_overflow == 3  # type: ignore[attr-defined]
    assert create_session_factory(engine).kw["expire_on_commit"] is False
    engine.dispose()
