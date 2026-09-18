from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt

from app.application.ports.services.security import AccessClaims, AccessToken
from app.domain.exceptions.errors import Unauthorized

TOKEN_TYPE = "access"


class JwtAccessTokenService:
    """JWT firmado (HS256) de vida corta. Solo lleva identidad y sesión: el rol se lee de la BD."""

    def __init__(self, secret_key: str, algorithm: str, ttl: timedelta) -> None:
        self._secret_key = secret_key
        self._algorithm = algorithm
        self._ttl = ttl

    def issue(self, user_id: UUID, session_id: UUID, now: datetime) -> AccessToken:
        issued_at = int(now.timestamp())
        expires_at = issued_at + int(self._ttl.total_seconds())
        payload = {
            "sub": str(user_id),
            "sid": str(session_id),
            "iat": issued_at,
            "exp": expires_at,
            "typ": TOKEN_TYPE,
        }
        return AccessToken(
            value=jwt.encode(payload, self._secret_key, algorithm=self._algorithm),
            expires_at=datetime.fromtimestamp(expires_at, UTC),
        )

    def decode(self, token: str) -> AccessClaims:
        try:
            payload = jwt.decode(
                token,
                self._secret_key,
                algorithms=[self._algorithm],  # fija el algoritmo: evita "alg: none"
                options={"require": ["exp", "iat", "sub", "sid"]},
            )
            if payload.get("typ") != TOKEN_TYPE:
                raise ValueError("tipo de token inesperado")
            return AccessClaims(user_id=UUID(payload["sub"]), session_id=UUID(payload["sid"]))
        except (jwt.PyJWTError, ValueError, KeyError, TypeError) as error:
            raise Unauthorized("Token inválido o expirado") from error
