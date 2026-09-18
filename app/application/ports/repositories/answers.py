from typing import Protocol
from uuid import UUID

from app.domain.forms.definition import FormVersion
from app.domain.forms.filled_form import FilledForm


class RequestAnswerRepository(Protocol):
    def load(self, request_id: UUID, form: FormVersion) -> FilledForm:
        """Respuestas guardadas de la solicitud, interpretadas con la versión de su formulario."""
        ...

    def replace(self, filled: FilledForm) -> None:
        """Deja guardadas exactamente estas respuestas (las anteriores se descartan)."""
        ...
