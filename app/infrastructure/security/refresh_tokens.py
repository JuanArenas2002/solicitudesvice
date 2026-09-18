import hashlib
import hmac
import secrets


class SecureRefreshTokenGenerator:
    """Token opaco de 256 bits; en BD solo su SHA-256 (con tanta entropía no requiere Argon2)."""

    def generate(self) -> str:
        return secrets.token_urlsafe(32)

    def hash(self, raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode()).hexdigest()


class HmacCsrfTokenService:
    """CSRF por doble envío ligado a la sesión: HMAC(clave, refresh token).

    El SPA lee la cookie `csrf_token` y la reenvía en `X-CSRF-Token`; el servidor la recalcula desde
    la cookie de refresh. Sin conocer el refresh token ni la clave, un atacante no puede forjarla.
    """

    def __init__(self, secret_key: str) -> None:
        # Clave derivada con separación de dominio: no se reutiliza tal cual la del JWT.
        self._key = hashlib.sha256(b"csrf|" + secret_key.encode()).digest()

    def issue(self, refresh_token: str) -> str:
        return hmac.new(self._key, refresh_token.encode(), hashlib.sha256).hexdigest()

    def verify(self, refresh_token: str, csrf_token: str) -> bool:
        return hmac.compare_digest(self.issue(refresh_token), csrf_token)
