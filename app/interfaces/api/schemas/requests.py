from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.application.dto.requests import RequestDetail, RequestSummary
from app.domain.entities.request_correction import RequestCorrection
from app.domain.entities.status_change import StatusChange
from app.domain.enums.correction_status import CorrectionStatus
from app.domain.enums.request_status import RequestStatus
from app.domain.services.request_workflow import EDITABLE_STATUSES
from app.interfaces.api.schemas.common import Input
from app.interfaces.api.schemas.forms import FormVersionOut, ProductTypeOut

AnswerIn = str | int | float | bool | list[str] | None
AnswerOut = str | int | Decimal | date | bool | list[str]


class CreateRequestIn(Input):
    product_type_id: int = Field(ge=1)


class AnswersUpdateIn(Input):
    version: int = Field(ge=1, description="Versión de la solicitud que el cliente tiene cargada")
    answers: dict[str, AnswerIn] = Field(
        max_length=200, description="clave del campo -> valor; null o vacío borra la respuesta"
    )


class ReasonIn(Input):
    reason: str | None = Field(default=None, max_length=2000)


class RequiredReasonIn(Input):
    reason: str = Field(min_length=1, max_length=2000)


class ChangeStatusIn(Input):
    status: RequestStatus
    reason: str = Field(min_length=1, max_length=2000, description="Motivo (queda en el historial)")


class CorrectionIn(Input):
    description: str = Field(min_length=1, max_length=2000)


class PersonOut(BaseModel):
    id: UUID
    name: str


class RequestSummaryOut(BaseModel):
    id: UUID
    request_number: str
    status: RequestStatus
    mentor: PersonOut
    product_type_id: int
    product_type_code: str
    product_type_name: str
    form_version_id: int
    version: int
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None
    reviewed_at: datetime | None

    @classmethod
    def of(cls, s: RequestSummary) -> "RequestSummaryOut":
        return cls(
            id=s.id,
            request_number=s.request_number,
            status=s.status,
            mentor=PersonOut(id=s.mentor_id, name=s.mentor_name),
            product_type_id=s.product_type_id,
            product_type_code=s.product_type_code,
            product_type_name=s.product_type_name,
            form_version_id=s.form_version_id,
            version=s.version,
            created_at=s.created_at,
            updated_at=s.updated_at,
            submitted_at=s.submitted_at,
            reviewed_at=s.reviewed_at,
        )


class CorrectionOut(BaseModel):
    id: UUID
    description: str
    status: CorrectionStatus
    requested_by: UUID
    created_at: datetime
    resolved_at: datetime | None

    @classmethod
    def of(cls, c: RequestCorrection) -> "CorrectionOut":
        return cls(
            id=c.id,
            description=c.description,
            status=c.status,
            requested_by=c.requested_by,
            created_at=c.created_at,
            resolved_at=c.resolved_at,
        )


class RequestDetailOut(BaseModel):
    id: UUID
    request_number: str
    status: RequestStatus
    mentor: PersonOut
    product_type: ProductTypeOut
    form_version_id: int
    version: int = Field(description="Enviar de vuelta en PATCH .../answers")
    is_editable: bool = Field(description="El dueño puede editar en este estado")
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None
    reviewed_at: datetime | None
    form: FormVersionOut
    answers: dict[str, AnswerOut]
    missing_required: list[str] = Field(description="Campos obligatorios aún sin respuesta")
    open_correction: CorrectionOut | None

    @classmethod
    def of(cls, d: RequestDetail) -> "RequestDetailOut":
        r = d.request
        open_correction = r.open_correction
        answers: dict[str, AnswerOut] = {
            key: list(value) if isinstance(value, tuple) else value
            for key, value in d.filled.answers.items()
        }
        return cls(
            id=r.id,
            request_number=str(r.request_number),
            status=r.status,
            mentor=PersonOut(id=r.mentor_id, name=d.mentor_name),
            product_type=ProductTypeOut.of(d.product_type),
            form_version_id=r.form_version_id,
            version=r.version,
            is_editable=r.status in EDITABLE_STATUSES,
            created_at=r.created_at,
            updated_at=r.updated_at,
            submitted_at=r.submitted_at,
            reviewed_at=r.reviewed_at,
            form=FormVersionOut.of(d.filled.form),
            answers=answers,
            missing_required=list(d.filled.missing_for_submission()),
            open_correction=CorrectionOut.of(open_correction) if open_correction else None,
        )


class HistoryEntryOut(BaseModel):
    previous_status: RequestStatus | None
    new_status: RequestStatus
    changed_by: UUID
    reason: str | None
    occurred_at: datetime

    @classmethod
    def of(cls, c: StatusChange) -> "HistoryEntryOut":
        return cls(
            previous_status=c.previous_status,
            new_status=c.new_status,
            changed_by=c.changed_by,
            reason=c.reason,
            occurred_at=c.occurred_at,
        )
