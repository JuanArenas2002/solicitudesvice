from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.domain.entities.research_product_request import ResearchProductRequest
from app.domain.enums.request_status import RequestStatus as S
from app.domain.enums.role import Role
from app.domain.forms.definition import FormVersion, SectionInput
from app.domain.forms.filled_form import FilledForm
from app.domain.value_objects.actor import Actor
from app.domain.value_objects.request_number import RequestNumber

NOW = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)

MENTOR = Actor(uuid4(), Role.MENTOR)
OTHER_MENTOR = Actor(uuid4(), Role.MENTOR)
STAFF = Actor(uuid4(), Role.ADMINISTRATIVO)
OTHER_STAFF = Actor(uuid4(), Role.ADMINISTRATIVO)
ADMIN = Actor(uuid4(), Role.ADMIN)

SAMPLE_SECTIONS: list[SectionInput] = [
    {
        "title": "Datos del artículo",
        "fields": [
            {"key": "cedula", "label": "Cédula", "type": "CEDULA", "required_to_submit": True},
            {"key": "titulo", "label": "Título", "type": "TEXT", "required_to_submit": True},
            {
                "key": "anio",
                "label": "Año",
                "type": "INTEGER",
                "required_to_submit": True,
                "min_value": 1900,
                "max_value": 2100,
            },
            {"key": "doi", "label": "DOI", "type": "DOI"},
        ],
    },
    {
        "title": "Revista",
        "fields": [
            {"key": "revista", "label": "Revista", "type": "TEXT", "required_to_submit": True},
            {"key": "issn", "label": "ISSN", "type": "ISSN"},
        ],
    },
]

COMPLETE_ANSWERS = {
    "cedula": "1003895357",
    "titulo": "Un estudio",
    "anio": 2025,
    "revista": "Revista de Pruebas",
}


def published_form() -> FormVersion:
    form = FormVersion.new(product_type_id=1, version_number=1, created_by=None, now=NOW)
    form.replace_structure(SAMPLE_SECTIONS)
    form.publish(NOW)
    return form


FORM = published_form()


def complete_form(request_id: UUID) -> FilledForm:
    return FilledForm.empty(request_id, FORM).apply(COMPLETE_ANSWERS)


def new_draft(mentor: Actor = MENTOR) -> ResearchProductRequest:
    request, _ = ResearchProductRequest.create_draft(
        actor=mentor,
        request_number=RequestNumber(2026, 1),
        form_version_id=1,
        product_type_id=1,
        now=NOW,
    )
    return request


def request_in(status: S, mentor: Actor = MENTOR, staff: Actor = STAFF) -> ResearchProductRequest:
    """Lleva una solicitud al estado pedido usando únicamente transiciones legales."""
    request = new_draft(mentor)
    article = complete_form(request.id)
    if status is S.BORRADOR:
        return request
    request.submit(mentor, NOW, article)
    if status is S.ENVIADA:
        return request
    request.start_review(staff, NOW)
    if status is S.EN_REVISION:
        return request
    if status is S.APROBADA:
        request.approve(staff, NOW)
    elif status is S.RECHAZADA:
        request.reject(staff, NOW, "No cumple")
    else:
        request.request_correction(staff, NOW, "Falta el DOI")
        if status is S.REENVIADA:
            request.resubmit(mentor, NOW, article)
    assert request.status is status
    return request
