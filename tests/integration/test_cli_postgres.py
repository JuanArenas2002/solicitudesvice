"""Comandos de administración (create-admin, seed-forms) contra PostgreSQL REAL."""

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app import cli
from app.config.settings import get_settings
from app.domain.enums.role import Role
from app.infrastructure.database.catalog import ROLE_IDS
from app.infrastructure.database.models import AuditLogModel, FormVersionModel, UserModel

pytestmark = pytest.mark.integration

PASSWORD = "clave-inicial-segura-1"


@pytest.fixture(autouse=True)
def cli_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    monkeypatch.setenv("JWT_SECRET_KEY", "k" * 48)
    monkeypatch.setenv("ADMIN_PASSWORD", PASSWORD)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def admin_args(email: str = "root@example.org") -> list[str]:
    return ["create-admin", "--email", email, "--first-name", "Root", "--last-name", "Admin"]


def test_create_admin_stores_an_argon2_hash_and_audits(
    engine: Engine, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(admin_args("  Root@Example.org ")) == 0
    with Session(engine) as session:
        (user,) = session.scalars(select(UserModel)).all()
        assert user.email == "root@example.org" and user.role_id == ROLE_IDS[Role.ADMIN]
        assert user.password_hash.startswith("$argon2id$") and PASSWORD not in user.password_hash
        assert user.is_active
        (audit,) = session.scalars(select(AuditLogModel)).all()
        assert audit.entity_id == user.id and audit.detail == {"role": "ADMIN", "bootstrap": True}
    assert "Administrador creado" in capsys.readouterr().out


def test_create_admin_rejects_weak_passwords_and_duplicates(
    engine: Engine, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ADMIN_PASSWORD", "corta")
    assert cli.main(admin_args()) == 1
    assert "contraseña" in capsys.readouterr().err
    monkeypatch.setenv("ADMIN_PASSWORD", PASSWORD)
    assert cli.main(admin_args()) == 0
    assert cli.main(admin_args()) == 1  # email repetido
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(UserModel)) == 1


def test_seed_forms_needs_an_admin_and_is_idempotent(
    engine: Engine, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["seed-forms"]) == 1
    assert "create-admin" in capsys.readouterr().err

    assert cli.main(admin_args()) == 0
    capsys.readouterr()
    assert cli.main(["seed-forms"]) == 0
    assert "cargado" in capsys.readouterr().out
    assert cli.main(["seed-forms"]) == 0
    assert "Ya estaba cargado" in capsys.readouterr().out
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(FormVersionModel)) == 1
