"""Repositorios SQLAlchemy, contador de solicitudes y UnitOfWork contra PostgreSQL REAL."""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.application.dto.page import PageRequest
from app.application.queries.users import UserFilter
from app.domain.entities.audit_entry import AuditEntry
from app.domain.entities.auth_session import AuthSession, RefreshToken
from app.domain.entities.user import User
from app.domain.enums.audit_action import AuditAction
from app.domain.enums.role import Role
from app.domain.exceptions.errors import DuplicateEmail, InvalidValue
from app.domain.value_objects.email import Email
from app.domain.value_objects.request_number import MAX_SEQUENCE
from app.infrastructure.database.models import (
    AuditLogModel,
    AuthSessionModel,
    RequestCounterModel,
    UserModel,
)
from app.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)


def make_user(
    email: str = "ana@example.org",
    role: Role = Role.MENTOR,
    first_name: str = "Ana",
    last_name: str = "Pérez",
    active: bool = True,
) -> User:
    user = User.create(
        first_name=first_name,
        last_name=last_name,
        email=email,
        password_hash="$argon2id$x",
        role=role,
        now=NOW,
    )
    user.is_active = active
    return user


def count(session_factory: sessionmaker[Session], model: type) -> int:
    with session_factory() as session:
        return session.scalar(select(func.count()).select_from(model)) or 0


# ---------------- usuarios ----------------
def test_user_roundtrip_and_lookup_by_email(session_factory: sessionmaker[Session]) -> None:
    user = make_user()
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.users.add(user)
        uow.commit()

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        by_id = uow.users.get(user.id)
        by_email = uow.users.get_by_email(Email.parse("ANA@example.org"))
        assert by_id is not None and by_email is not None
        assert by_id.id == by_email.id == user.id
        assert (by_id.first_name, by_id.role, by_id.is_active) == ("Ana", Role.MENTOR, True)
        assert by_id.created_at == NOW and by_id.last_login_at is None
        assert uow.users.get_by_email(Email.parse("nadie@example.org")) is None


def test_user_updates_are_persisted(session_factory: sessionmaker[Session]) -> None:
    user = make_user()
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.users.add(user)
        uow.commit()
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        loaded = uow.users.get(user.id)
        assert loaded is not None
        loaded.update_profile(NOW + timedelta(hours=1), first_name="Ana María", role=Role.ADMIN)
        loaded.set_active(False, NOW + timedelta(hours=1))
        loaded.record_login(NOW + timedelta(hours=2))
        uow.users.save(loaded)
        uow.commit()
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        again = uow.users.get(user.id)
        assert again is not None
        assert (again.first_name, again.role, again.is_active) == ("Ana María", Role.ADMIN, False)
        assert again.last_login_at == NOW + timedelta(hours=2)


def test_duplicate_email_is_translated_to_a_domain_error(
    session_factory: sessionmaker[Session],
) -> None:
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.users.add(make_user("dup@example.org"))
        uow.commit()
    with SqlAlchemyUnitOfWork(session_factory) as uow, pytest.raises(DuplicateEmail):
        uow.users.add(make_user("dup@example.org"))
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        other = make_user("otro@example.org")
        uow.users.add(other)
        uow.commit()
        other.update_profile(NOW, email="dup@example.org")
        with pytest.raises(DuplicateEmail):
            uow.users.save(other)


def test_list_users_filters_orders_paginates_and_escapes_wildcards(
    session_factory: sessionmaker[Session],
) -> None:
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        for i in range(12):
            uow.users.add(
                make_user(f"m{i:02d}@example.org", last_name="Zeta", first_name=f"M{i:02d}")
            )
        uow.users.add(make_user("carla@example.org", Role.ADMINISTRATIVO, "Carla", "Alfa"))
        uow.users.add(
            make_user("off@example.org", first_name="Off", last_name="Zeta", active=False)
        )
        uow.users.add(make_user("100%@example.org", first_name="Pct", last_name="Beta"))
        uow.commit()

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        mentors = uow.users.list(UserFilter(role=Role.MENTOR, is_active=True), PageRequest(1, 5))
        assert (mentors.total, len(mentors.items), mentors.total_pages) == (13, 5, 3)
        everyone = uow.users.list(UserFilter(), PageRequest(1, 100))
        assert everyone.total == 15 and everyone.items[0].last_name == "Alfa"
        page3 = uow.users.list(UserFilter(role=Role.MENTOR, is_active=True), PageRequest(3, 5))
        assert len(page3.items) == 3
        assert [
            u.first_name for u in uow.users.list(UserFilter(search="CARLA"), PageRequest()).items
        ] == ["Carla"]
        # '%' se trata como carácter literal, no como comodín
        assert [
            u.first_name for u in uow.users.list(UserFilter(search="100%"), PageRequest()).items
        ] == ["Pct"]
        assert uow.users.list(UserFilter(search="%"), PageRequest()).total == 1


# ---------------- sesiones y refresh tokens ----------------
def _session_with_token(
    uow: SqlAlchemyUnitOfWork, user: User, hash_char: str = "a"
) -> tuple[AuthSession, RefreshToken]:
    session = AuthSession(user_id=user.id, created_at=NOW, expires_at=NOW + timedelta(days=30))
    token = RefreshToken(
        session_id=session.id,
        token_hash=hash_char * 64,
        created_at=NOW,
        expires_at=NOW + timedelta(days=7),
    )
    uow.sessions.add_session(session)
    uow.sessions.add_refresh_token(token)
    return session, token


def test_sessions_and_refresh_tokens_roundtrip(session_factory: sessionmaker[Session]) -> None:
    user = make_user()
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.users.add(user)
        session, token = _session_with_token(uow, user)
        uow.commit()

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        stored = uow.sessions.get_refresh_token_for_update("a" * 64)
        assert stored is not None and stored.session_id == session.id and stored.used_at is None
        assert uow.sessions.get_refresh_token_for_update("b" * 64) is None
        stored.consume(NOW)
        uow.sessions.save_refresh_token(stored)
        loaded = uow.sessions.get_session(session.id)
        assert loaded is not None and loaded.is_active(NOW)
        loaded.revoke(NOW, "LOGOUT")
        uow.sessions.save_session(loaded)
        uow.commit()

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert uow.sessions.get_refresh_token_for_update("a" * 64).used_at == NOW  # type: ignore[union-attr]
        revoked = uow.sessions.get_session(session.id)
        assert (
            revoked is not None
            and revoked.revoked_reason == "LOGOUT"
            and not revoked.is_active(NOW)
        )
        assert uow.sessions.get_session(token.id) is None  # id inexistente


def test_revoke_all_for_user_skips_the_excepted_session_and_other_users(
    session_factory: sessionmaker[Session],
) -> None:
    ana, luis = make_user("ana@example.org"), make_user("luis@example.org")
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.users.add(ana)
        uow.users.add(luis)
        keep, _ = _session_with_token(uow, ana, "a")
        drop1, _ = _session_with_token(uow, ana, "b")
        drop2, _ = _session_with_token(uow, ana, "c")
        others, _ = _session_with_token(uow, luis, "d")
        uow.commit()

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        revoked = uow.sessions.revoke_all_for_user(
            ana.id, NOW, "PASSWORD_CHANGED", except_session_id=keep.id
        )
        assert revoked == 2
        assert (
            uow.sessions.revoke_all_for_user(ana.id, NOW, "X", except_session_id=keep.id) == 0
        )  # idempotente
        uow.commit()

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert uow.sessions.get_session(keep.id).revoked_at is None  # type: ignore[union-attr]
        assert uow.sessions.get_session(others.id).revoked_at is None  # type: ignore[union-attr]
        for dropped in (drop1, drop2):
            assert uow.sessions.get_session(dropped.id).revoked_reason == "PASSWORD_CHANGED"  # type: ignore[union-attr]


# ---------------- auditoría ----------------
def test_audit_entries_are_appended_with_inet_ip_and_json_detail(
    session_factory: sessionmaker[Session],
) -> None:
    user = make_user()
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.users.add(user)
        uow.audit.add(
            AuditEntry(
                AuditAction.USER_UPDATED,
                NOW,
                actor_id=user.id,
                entity_id=user.id,
                correlation_id="abc-123",
                ip_address="203.0.113.7",
                detail={"changed": ["first_name", "role"]},
            )
        )
        uow.audit.add(AuditEntry(AuditAction.LOGIN_FAILED, NOW, detail={"reason": "unknown_user"}))
        uow.commit()

    with session_factory() as session:
        rows = session.scalars(select(AuditLogModel).order_by(AuditLogModel.id)).all()
        assert [r.action_id for r in rows] == [
            9,
            2,
        ]  # USER_UPDATED, LOGIN_FAILED (ids del catálogo)
        assert rows[0].detail == {"changed": ["first_name", "role"]}
        assert rows[0].correlation_id == "abc-123" and str(rows[0].ip_address) == "203.0.113.7"
        assert rows[1].actor_id is None and rows[1].entity_id is None and rows[1].ip_address is None
        assert rows[0].id < rows[1].id  # PK secuencial


# ---------------- transacciones ----------------
def test_leaving_the_block_without_commit_rolls_everything_back(
    session_factory: sessionmaker[Session],
) -> None:
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.users.add(make_user())
        uow.audit.add(AuditEntry(AuditAction.USER_CREATED, NOW))
    assert count(session_factory, UserModel) == 0 and count(session_factory, AuditLogModel) == 0


def test_an_exception_rolls_back_user_and_audit_together(
    session_factory: sessionmaker[Session],
) -> None:
    with pytest.raises(RuntimeError), SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.users.add(make_user())
        uow.audit.add(AuditEntry(AuditAction.USER_CREATED, NOW))
        raise RuntimeError("falla a mitad de la operación")
    assert count(session_factory, UserModel) == 0 and count(session_factory, AuditLogModel) == 0


def test_commit_makes_everything_visible_atomically(session_factory: sessionmaker[Session]) -> None:
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.users.add(make_user())
        uow.audit.add(AuditEntry(AuditAction.USER_CREATED, NOW))
        uow.commit()
    assert count(session_factory, UserModel) == 1 and count(session_factory, AuditLogModel) == 1


def test_commit_outside_a_with_block_is_an_error(session_factory: sessionmaker[Session]) -> None:
    with pytest.raises(RuntimeError):
        SqlAlchemyUnitOfWork(session_factory).commit()


# ---------------- número de solicitud ----------------
def test_request_numbers_are_sequential_per_year(session_factory: sessionmaker[Session]) -> None:
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        numbers = [str(uow.request_numbers.next(2026)) for _ in range(3)]
        first_of_next_year = str(uow.request_numbers.next(2027))
        uow.commit()
    assert numbers == ["SOL-2026-000001", "SOL-2026-000002", "SOL-2026-000003"]
    assert first_of_next_year == "SOL-2027-000001"  # cada año reinicia
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert str(uow.request_numbers.next(2026)) == "SOL-2026-000004"  # continúa tras el commit


def test_a_rolled_back_transaction_does_not_burn_a_number(
    session_factory: sessionmaker[Session],
) -> None:
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert str(uow.request_numbers.next(2026)) == "SOL-2026-000001"
        uow.commit()
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert str(uow.request_numbers.next(2026)) == "SOL-2026-000002"
        # sin commit: rollback
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert str(uow.request_numbers.next(2026)) == "SOL-2026-000002"  # sin huecos


@pytest.mark.parametrize("start_year_exists", [True, False])
def test_concurrent_creations_never_repeat_or_skip_a_number(
    session_factory: sessionmaker[Session], start_year_exists: bool
) -> None:
    """12 transacciones simultáneas (incluida la carrera por crear el contador del año)."""
    if start_year_exists:
        with SqlAlchemyUnitOfWork(session_factory) as uow:
            uow.request_numbers.next(2026)
            uow.commit()
    workers = 12
    barrier = threading.Barrier(workers)

    def take() -> int:
        with SqlAlchemyUnitOfWork(session_factory) as uow:
            barrier.wait()  # todas a la vez
            number = uow.request_numbers.next(2026)
            uow.commit()
            return number.sequence

    with ThreadPoolExecutor(max_workers=workers) as pool:
        taken = sorted(pool.map(lambda _: take(), range(workers)))

    first = 2 if start_year_exists else 1
    assert taken == list(range(first, first + workers))


def test_the_counter_stops_at_the_maximum_and_rolls_back(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        session.add(RequestCounterModel(year=2030, last_value=MAX_SEQUENCE))
        session.commit()
    with pytest.raises(InvalidValue), SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.request_numbers.next(2030)
    with session_factory() as session:
        counter = session.get(RequestCounterModel, 2030)
        assert counter is not None and counter.last_value == MAX_SEQUENCE  # no quedó incrementado


def test_sessions_table_keeps_sessions_of_deactivated_users(
    session_factory: sessionmaker[Session],
) -> None:
    user = make_user(active=False)
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.users.add(user)
        _session_with_token(uow, user)
        uow.commit()
    assert count(session_factory, AuthSessionModel) == 1  # nada se borra físicamente
