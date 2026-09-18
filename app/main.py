"""Punto de entrada ASGI:  uvicorn app.main:app"""

from app.interfaces.api.app import create_app

app = create_app()
