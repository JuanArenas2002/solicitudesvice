import logging
from collections.abc import Collection

from app.application.ports.services.journals import Journal, JournalCatalog
from app.domain.enums.permission import Permission
from app.domain.exceptions.errors import InvalidValue, JournalNotFound, JournalServiceUnavailable
from app.domain.forms.field_types import ISSN
from app.domain.forms.filled_form import FilledForm
from app.domain.services.authorizer import require_permission
from app.domain.value_objects.actor import Actor
from app.domain.value_objects.identifiers import Issn

log = logging.getLogger("app.journals")


class LookupJournal:
    """Consulta una revista por ISSN (para que la interfaz muestre su nombre al escribirlo)."""

    def __init__(self, journals: JournalCatalog | None) -> None:
        self._journals = journals

    def execute(self, actor: Actor, issn: str) -> Journal:
        require_permission(actor, Permission.VIEW_FORMS)
        normalized = Issn.parse(issn).value  # InvalidValue si el formato no es de un ISSN
        if self._journals is None:
            raise JournalServiceUnavailable("La validación de revistas no está habilitada")
        journal = self._journals.find(normalized)
        if journal is None:
            raise JournalNotFound(f"El ISSN {normalized} no está registrado como revista")
        return journal


def verify_issns(
    journals: JournalCatalog | None,
    filled: FilledForm,
    keys: Collection[str] | None,
    *,
    strict: bool,
) -> None:
    """Valida contra el catálogo los campos ISSN respondidos (keys=None: todos).

    Un ISSN que el catálogo no conoce se rechaza siempre. Si el catálogo no responde: con
    strict (al enviar) se rechaza pidiendo reintentar; sin él (al guardar borrador) se acepta.
    """
    if journals is None:
        return
    for field in filled.form.fields():
        value = filled.answers.get(field.key)
        if field.type_code != ISSN or not isinstance(value, str):
            continue
        if keys is not None and field.key not in keys:
            continue
        try:
            journal = journals.find(value)
        except JournalServiceUnavailable:
            if strict:
                raise JournalServiceUnavailable(
                    f"No se pudo verificar el ISSN de «{field.label}» en el catálogo de revistas. "
                    "Intente enviar de nuevo en unos minutos."
                ) from None
            log.warning("Catálogo de revistas no disponible; ISSN sin verificar")
            continue
        if journal is None:
            raise InvalidValue(
                f"{field.label}: el ISSN {value} no está registrado en el catálogo de revistas",
                field=field.key,
            )
