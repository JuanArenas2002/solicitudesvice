from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest

from app.domain.entities.attachment import Attachment
from app.domain.entities.audit_entry import AuditEntry
from app.domain.entities.auth_session import AuthSession, RefreshToken
from app.domain.entities.request_correction import RequestCorrection
from app.domain.entities.user import User
from app.domain.enums.audit_action import AuditAction, AuditCategory
from app.domain.enums.correction_status import CorrectionStatus
from app.domain.enums.role import Role
from app.domain.exceptions.errors import (
    InvalidRequestState,
    InvalidValue,
    RefreshTokenReuse,
    Unauthorized,
)
from tests.unit.domain.factories import NOW


def make_user(**overrides) -> User:
    data = {
        "first_name": " Ana ",
        "last_name": "Pérez",
        "email": " ANA@Example.org",
        "password_hash": "$argon2id$hash",
        "role": Role.MENTOR,
        "now": NOW,
    }
    return User.create(**{**data, **overrides})


def test_user_is_created_normalized_and_active() -> None:
    user = make_user()
    assert (user.first_name, str(user.email), user.is_active) == ("Ana", "ana@example.org", True)
    assert user.created_at == user.updated_at == NOW and user.last_login_at is None


def test_user_rejects_blank_names_and_bad_email() -> None:
    for overrides in ({"first_name": " "}, {"last_name": ""}, {"email": "x"}):
        with pytest.raises(InvalidValue):
            make_user(**overrides)


def test_user_updates_and_soft_disable() -> None:
    user = make_user()
    later = NOW + timedelta(hours=1)
    user.update_profile(
        later, first_name="Ana María", email="NUEVO@x.org", role=Role.ADMINISTRATIVO
    )
    assert (user.first_name, str(user.email), user.role) == (
        "Ana María",
        "nuevo@x.org",
        Role.ADMINISTRATIVO,
    )
    assert user.last_name == "Pérez"  # no enviado: no cambia
    user.set_active(False, later)
    assert user.is_active is False and user.updated_at == later
    user.record_login(later)
    assert user.last_login_at == later


def test_session_lifecycle_and_idempotent_revocation() -> None:
    session = AuthSession(user_id=uuid4(), created_at=NOW, expires_at=NOW + timedelta(days=1))
    assert session.is_active(NOW)
    assert not session.is_active(NOW + timedelta(days=1))
    session.revoke(NOW, "LOGOUT")
    session.revoke(NOW + timedelta(hours=1), "OTHER")
    assert not session.is_active(NOW)
    assert session.revoked_reason == "LOGOUT" and session.revoked_at == NOW


def test_refresh_token_rotation_and_reuse_detection() -> None:
    token = RefreshToken(uuid4(), "a" * 64, NOW, NOW + timedelta(days=7))
    token.consume(NOW)
    assert token.used_at == NOW
    with pytest.raises(RefreshTokenReuse):
        token.consume(NOW + timedelta(seconds=1))
    assert issubclass(RefreshTokenReuse, Unauthorized)


def test_expired_refresh_token_is_rejected() -> None:
    token = RefreshToken(uuid4(), "a" * 64, NOW, NOW + timedelta(days=7))
    with pytest.raises(Unauthorized):
        token.consume(NOW + timedelta(days=7))
    assert token.used_at is None


def test_correction_open_and_resolve_once() -> None:
    correction = RequestCorrection.open(uuid4(), uuid4(), "  Falta el DOI ", NOW)
    assert correction.is_open and correction.description == "Falta el DOI"
    correction.resolve(NOW)
    assert correction.status is CorrectionStatus.RESUELTA and correction.resolved_at == NOW
    with pytest.raises(InvalidRequestState):
        correction.resolve(NOW)
    with pytest.raises(InvalidValue):
        RequestCorrection.open(uuid4(), uuid4(), "  ", NOW)


def test_attachment_validation() -> None:
    valid: dict[str, Any] = {
        "request_id": uuid4(),
        "field_id": 7,
        "field_key": "soporte",
        "uploaded_by": uuid4(),
        "file_name": "articulo.pdf",
        "storage_key": "2026/abc",
        "mime_type": "application/pdf",
        "file_size": 10,
        "sha256": "a" * 64,
        "created_at": NOW,
    }
    Attachment(**valid)
    for override in (
        {"file_size": 0},
        {"file_name": " "},
        {"storage_key": ""},
        {"sha256": "corta"},
        {"sha256": "G" * 64},
    ):
        with pytest.raises(InvalidValue):
            Attachment(**{**valid, **override})


@pytest.mark.parametrize(
    "detail",
    [
        {"password": "x"},
        {"new_password": "x"},
        {"refresh_token": "abc"},
        {"nested": {"Authorization": "Bearer x"}},
        {"items": [{"secret_key": "x"}]},
        {"cookie": "x"},
    ],
)
def test_audit_entries_never_carry_secrets(detail) -> None:
    with pytest.raises(InvalidValue):
        AuditEntry(AuditAction.LOGIN_FAILED, NOW, detail=detail)


def test_audit_entry_accepts_safe_detail_and_has_categories() -> None:
    AuditEntry(AuditAction.REQUEST_UPDATED, NOW, detail={"changed": ["title", "doi"]})
    assert AuditAction.LOGIN_FAILED.category is AuditCategory.SECURITY
    assert AuditAction.USER_DEACTIVATED.category is AuditCategory.SECURITY
    assert AuditAction.REQUEST_APPROVED.category is AuditCategory.REQUESTS
    assert AuditAction.ATTACHMENT_UPLOADED.category is AuditCategory.REQUESTS
    assert AuditAction.FORM_PUBLISHED.category is AuditCategory.CONFIGURATION
    assert AuditAction.PRODUCT_TYPE_CREATED.entity_type == "product_type"
    assert AuditAction.FORM_DRAFT_SAVED.entity_type == "form_version"
    assert AuditAction.LOGIN_FAILED.entity_type == "session"
    assert AuditAction.USER_CREATED.entity_type == "user"
    assert AuditAction.REVIEW_STARTED.entity_type == "request"
    assert AuditAction.ATTACHMENT_DELETED.entity_type == "attachment"
