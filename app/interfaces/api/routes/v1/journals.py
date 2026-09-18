from fastapi import APIRouter
from pydantic import BaseModel

from app.interfaces.api.dependencies import ActorDep, ContainerDep

router = APIRouter(prefix="/journals", tags=["journals"])


class JournalOut(BaseModel):
    title: str
    publisher: str | None
    country: str | None
    issn_print: str | None
    eissn: str | None
    open_access: bool | None


@router.get(
    "/{issn}",
    response_model=JournalOut,
    summary="Revista por ISSN (catálogo institucional); 404 si no existe",
)
def get_journal(issn: str, actor: ActorDep, container: ContainerDep) -> JournalOut:
    journal = container.lookup_journal().execute(actor, issn)
    return JournalOut(
        title=journal.title,
        publisher=journal.publisher,
        country=journal.country,
        issn_print=journal.issn_print,
        eissn=journal.eissn,
        open_access=journal.open_access,
    )
