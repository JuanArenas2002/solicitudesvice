"""Catálogo de revistas por HTTP (servicio institucional de Metri-K)."""

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from threading import Lock

from app.application.ports.services.journals import Journal
from app.domain.exceptions.errors import JournalServiceUnavailable

log = logging.getLogger("app.journals")

CACHE_SECONDS = 3600  # una revista no cambia de un momento a otro; evita repetir la consulta


class HttpJournalCatalog:
    """GET {base_url}/{issn}: 200 = existe, 404 = no existe, cualquier otra cosa = no disponible."""

    def __init__(self, base_url: str, timeout_seconds: float = 4.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._cache: dict[str, tuple[float, Journal | None]] = {}
        self._lock = Lock()

    def find(self, issn: str) -> Journal | None:
        now = time.monotonic()
        with self._lock:
            cached = self._cache.get(issn)
        if cached is not None and now - cached[0] < CACHE_SECONDS:
            return cached[1]
        journal = self._fetch(issn)
        with self._lock:
            self._cache[issn] = (now, journal)  # también se recuerda "no existe"
        return journal

    def _fetch(self, issn: str) -> Journal | None:
        url = f"{self._base_url}/{urllib.parse.quote(issn, safe='')}"
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:  # noqa: S310
                body = json.load(response)
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            log.warning("Catálogo de revistas respondió %s", error.code)
            raise JournalServiceUnavailable("El catálogo de revistas no está disponible") from None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
            log.warning("Catálogo de revistas inalcanzable: %s", type(error).__name__)
            raise JournalServiceUnavailable("El catálogo de revistas no está disponible") from None
        if not isinstance(body, dict) or not isinstance(body.get("titulo"), str):
            raise JournalServiceUnavailable(
                "El catálogo de revistas devolvió una respuesta inválida"
            )

        def text(key: str) -> str | None:
            value = body.get(key)
            return value if isinstance(value, str) and value else None

        open_access = body.get("open_access")
        return Journal(
            title=body["titulo"],
            publisher=text("editorial"),
            country=text("pais"),
            issn_print=text("issn_print"),
            eissn=text("eissn"),
            open_access=open_access if isinstance(open_access, bool) else None,
        )
