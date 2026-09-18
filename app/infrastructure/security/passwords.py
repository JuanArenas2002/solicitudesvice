from functools import lru_cache

from argon2 import PasswordHasher as Argon2
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError


@lru_cache
def _dummy_hash() -> str:
    return Argon2().hash("contraseña-inexistente")


class Argon2PasswordHasher:
    """Argon2id (el tipo por defecto de argon2-cffi) con parámetros actuales de la librería."""

    def __init__(self, hasher: Argon2 | None = None) -> None:
        self._hasher = hasher or Argon2()

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, password_hash: str, password: str) -> bool:
        try:
            return self._hasher.verify(password_hash, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    def needs_rehash(self, password_hash: str) -> bool:
        return self._hasher.check_needs_rehash(password_hash)

    def verify_dummy(self, password: str) -> None:
        self.verify(_dummy_hash(), password)
