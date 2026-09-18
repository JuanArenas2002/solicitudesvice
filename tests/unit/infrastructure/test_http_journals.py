"""Adaptador HTTP del catálogo de revistas contra un servidor local (sin tocar la red real)."""

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import ClassVar

import pytest

from app.domain.exceptions.errors import JournalServiceUnavailable
from app.infrastructure.journals.http import HttpJournalCatalog

NATURE = {
    "titulo": "Nature",
    "editorial": "Nature Research",
    "pais": "United Kingdom",
    "issn_print": "00280836",
    "eissn": "14764687",
    "open_access": False,
    "metricas_anuales": [{"anio": 2020}],  # datos de sobra: se ignoran
}


class Handler(BaseHTTPRequestHandler):
    hits: ClassVar[list[str]] = []
    behaviour: ClassVar[str] = "ok"

    def do_GET(self) -> None:  # noqa: N802
        Handler.hits.append(self.path)
        issn = self.path.rsplit("/", 1)[-1]
        if Handler.behaviour == "error":
            self.send_response(500)
            self.end_headers()
            return
        if Handler.behaviour == "garbage":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"<html>no soy json</html>")
            return
        if Handler.behaviour == "no-title":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps({"editorial": "x"}).encode())
            return
        if issn == "0028-0836":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps(NATURE).encode())
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(json.dumps({"detail": "Revista no encontrada"}).encode())

    def log_message(self, *args: object) -> None:  # silencia el log del servidor
        pass


@pytest.fixture
def server() -> Iterator[str]:
    Handler.hits.clear()
    Handler.behaviour = "ok"
    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}/revistas/revistas"
    httpd.shutdown()


def test_an_existing_journal_is_described(server: str) -> None:
    journal = HttpJournalCatalog(server).find("0028-0836")
    assert journal is not None
    assert (journal.title, journal.publisher, journal.country) == (
        "Nature",
        "Nature Research",
        "United Kingdom",
    )
    assert (journal.issn_print, journal.eissn, journal.open_access) == (
        "00280836",
        "14764687",
        False,
    )
    assert Handler.hits == ["/revistas/revistas/0028-0836"]


def test_a_missing_journal_is_none_not_an_error(server: str) -> None:
    assert HttpJournalCatalog(server).find("0000-0000") is None


def test_answers_are_cached_including_not_found(server: str) -> None:
    catalog = HttpJournalCatalog(server)
    catalog.find("0028-0836")
    catalog.find("0028-0836")
    catalog.find("0000-0000")
    catalog.find("0000-0000")
    assert len(Handler.hits) == 2


@pytest.mark.parametrize("behaviour", ["error", "garbage", "no-title"])
def test_a_broken_service_means_unavailable_and_is_not_cached(server: str, behaviour: str) -> None:
    Handler.behaviour = behaviour
    catalog = HttpJournalCatalog(server)
    with pytest.raises(JournalServiceUnavailable):
        catalog.find("0028-0836")
    Handler.behaviour = "ok"  # se recupera: el fallo no quedó guardado
    assert catalog.find("0028-0836") is not None


def test_an_unreachable_service_means_unavailable() -> None:
    catalog = HttpJournalCatalog("http://127.0.0.1:9/revistas", timeout_seconds=0.5)
    with pytest.raises(JournalServiceUnavailable):
        catalog.find("0028-0836")


def test_the_issn_is_url_encoded(server: str) -> None:
    HttpJournalCatalog(server).find("../secreto")
    assert Handler.hits == ["/revistas/revistas/..%2Fsecreto"]
