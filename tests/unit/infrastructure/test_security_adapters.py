import base64
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from argon2 import PasswordHasher as Argon2

from app.domain.exceptions.errors import Unauthorized
from app.infrastructure.security.access_tokens import JwtAccessTokenService
from app.infrastructure.security.passwords import Argon2PasswordHasher
from app.infrastructure.security.refresh_tokens import (
    HmacCsrfTokenService,
    SecureRefreshTokenGenerator,
)

SECRET = "s" * 40
NOW = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)


# ---------------- Argon2id ----------------
def test_argon2id_hashes_and_verifies() -> None:
    hasher = Argon2PasswordHasher()
    password_hash = hasher.hash("una-clave-segura")
    assert password_hash.startswith("$argon2id$")
    assert "una-clave-segura" not in password_hash
    assert hasher.hash("una-clave-segura") != password_hash  # salt aleatoria
    assert hasher.verify(password_hash, "una-clave-segura")
    assert not hasher.verify(password_hash, "otra")
    assert not hasher.needs_rehash(password_hash)


@pytest.mark.parametrize("garbage", ["", "no-es-un-hash", "$argon2id$roto"])
def test_verify_never_raises_on_invalid_hashes(garbage: str) -> None:
    assert Argon2PasswordHasher().verify(garbage, "x") is False


def test_needs_rehash_detects_weaker_parameters() -> None:
    weak = Argon2(time_cost=1, memory_cost=8, parallelism=1).hash("clave")
    assert Argon2PasswordHasher().needs_rehash(weak)


def test_dummy_verification_runs_without_error() -> None:
    Argon2PasswordHasher().verify_dummy("lo-que-sea")


# ---------------- JWT ----------------
def service(secret: str = SECRET, ttl: timedelta = timedelta(minutes=15)) -> JwtAccessTokenService:
    return JwtAccessTokenService(secret, "HS256", ttl)


def test_jwt_roundtrip_carries_only_identity_and_session() -> None:
    user_id, session_id = uuid4(), uuid4()
    token = service().issue(user_id, session_id, datetime.now(UTC))
    claims = service().decode(token.value)
    assert (claims.user_id, claims.session_id) == (user_id, session_id)
    payload = jwt.decode(token.value, options={"verify_signature": False})
    assert set(payload) == {"sub", "sid", "iat", "exp", "typ"}  # sin rol ni datos personales


def test_jwt_expiry_is_enforced() -> None:
    token = service().issue(uuid4(), uuid4(), NOW - timedelta(hours=1))  # emitido hace una hora
    with pytest.raises(Unauthorized):
        service().decode(token.value)
    assert token.expires_at == NOW - timedelta(minutes=45)


def test_jwt_rejects_tampering_wrong_key_and_garbage() -> None:
    token = service().issue(uuid4(), uuid4(), datetime.now(UTC)).value
    header, payload, signature = token.split(".")
    forged_payload = base64.urlsafe_b64encode(
        json.dumps(
            {**json.loads(base64.urlsafe_b64decode(payload + "==")), "sub": str(uuid4())}
        ).encode()
    ).rstrip(b"=")
    for bad in (
        f"{header}.{forged_payload.decode()}.{signature}",  # payload alterado
        token[:-3] + "abc",  # firma alterada
        "no-es-un-jwt",
        "",
    ):
        with pytest.raises(Unauthorized):
            service().decode(bad)
    with pytest.raises(Unauthorized):
        service(secret="x" * 40).decode(token)  # otra clave


def test_jwt_rejects_alg_none_missing_claims_and_wrong_type() -> None:
    def encode(payload: dict[str, object], algorithm: str = "HS256") -> str:
        key = None if algorithm == "none" else SECRET
        return jwt.encode(payload, key, algorithm=algorithm)

    exp = int((datetime.now(UTC) + timedelta(minutes=5)).timestamp())
    base = {"sub": str(uuid4()), "sid": str(uuid4()), "iat": 1, "exp": exp, "typ": "access"}
    assert service().decode(encode(base)).user_id  # control positivo

    with pytest.raises(Unauthorized):
        service().decode(encode(base, algorithm="none"))
    for missing in ("sub", "sid", "exp", "iat"):
        with pytest.raises(Unauthorized):
            service().decode(encode({k: v for k, v in base.items() if k != missing}))
    with pytest.raises(Unauthorized):
        service().decode(encode({**base, "typ": "refresh"}))
    with pytest.raises(Unauthorized):
        service().decode(encode({**base, "sub": "no-uuid"}))


# ---------------- refresh token y CSRF ----------------
def test_refresh_tokens_are_random_and_only_the_hash_is_derivable() -> None:
    generator = SecureRefreshTokenGenerator()
    tokens = {generator.generate() for _ in range(200)}
    assert len(tokens) == 200 and all(len(t) >= 43 for t in tokens)  # >= 256 bits
    raw = next(iter(tokens))
    digest = generator.hash(raw)
    assert len(digest) == 64 and digest == generator.hash(raw) and raw not in digest
    assert int(digest, 16) >= 0  # hexadecimal


def test_csrf_token_is_bound_to_the_refresh_token() -> None:
    csrf = HmacCsrfTokenService(SECRET)
    token = csrf.issue("refresh-A")
    assert csrf.verify("refresh-A", token)
    assert not csrf.verify("refresh-B", token)  # ligado a la sesión
    assert not csrf.verify("refresh-A", token[:-1] + ("0" if token[-1] != "0" else "1"))
    assert not csrf.verify("refresh-A", "")
    assert HmacCsrfTokenService("otra-clave-" * 4).issue("refresh-A") != token
    assert csrf.issue("refresh-A") == token  # determinista: se recalcula en el servidor
