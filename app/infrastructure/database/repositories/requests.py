from datetime import UTC, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.application.dto.page import Page, PageRequest
from app.application.dto.requests import RequestSummary
from app.application.queries.requests import RequestFilter
from app.domain.entities.request_correction import RequestCorrection
from app.domain.entities.research_product_request import ResearchProductRequest
from app.domain.enums.request_status import RequestStatus
from app.domain.exceptions.errors import ConcurrentModification
from app.domain.services.access_policy import RequestScope
from app.domain.value_objects.request_number import RequestNumber
from app.infrastructure.database.catalog import (
    CORRECTION_STATUS_IDS,
    REQUEST_STATUS_BY_ID,
    REQUEST_STATUS_IDS,
)
from app.infrastructure.database.models.form import FormVersionModel
from app.infrastructure.database.models.product_type import ProductTypeModel
from app.infrastructure.database.models.request_correction import RequestCorrectionModel
from app.infrastructure.database.models.research_request import ResearchProductRequestModel
from app.infrastructure.database.models.user import UserModel

_CORRECTION_STATUS_BY_ID = {i: s for s, i in CORRECTION_STATUS_IDS.items()}


def _correction_entity(m: RequestCorrectionModel) -> RequestCorrection:
    return RequestCorrection(
        id=m.id,
        request_id=m.request_id,
        requested_by=m.requested_by,
        description=m.description,
        created_at=m.created_at,
        status=_CORRECTION_STATUS_BY_ID[m.status_id],
        resolved_at=m.resolved_at,
    )


def _apply(model: ResearchProductRequestModel, request: ResearchProductRequest) -> None:
    model.status_id = REQUEST_STATUS_IDS[request.status]
    model.reviewer_id = request.reviewer_id
    model.submitted_at = request.submitted_at
    model.reviewed_at = request.reviewed_at
    model.updated_at = request.updated_at


class SqlAlchemyRequestRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, request: ResearchProductRequest) -> None:
        model = ResearchProductRequestModel(
            id=request.id,
            request_number=str(request.request_number),
            mentor_id=request.mentor_id,
            form_version_id=request.form_version_id,
            created_at=request.created_at,
        )
        _apply(model, request)
        self._session.add(model)
        self._session.flush()
        self._sync_corrections(request)
        request.version = model.version

    def get(self, request_id: UUID, *, for_update: bool = False) -> ResearchProductRequest | None:
        query = (
            select(ResearchProductRequestModel, FormVersionModel.product_type_id)
            .join(
                FormVersionModel, FormVersionModel.id == ResearchProductRequestModel.form_version_id
            )
            .where(ResearchProductRequestModel.id == request_id)
            .execution_options(populate_existing=True)
        )
        if for_update:
            query = query.with_for_update(of=ResearchProductRequestModel)
        row = self._session.execute(query).one_or_none()
        if row is None:
            return None
        model, product_type_id = row
        corrections = self._session.scalars(
            select(RequestCorrectionModel)
            .where(RequestCorrectionModel.request_id == request_id)
            .order_by(RequestCorrectionModel.created_at, RequestCorrectionModel.id)
        ).all()
        return ResearchProductRequest(
            id=model.id,
            request_number=RequestNumber.parse(model.request_number),
            mentor_id=model.mentor_id,
            form_version_id=model.form_version_id,
            product_type_id=product_type_id,
            status=REQUEST_STATUS_BY_ID[model.status_id],
            created_at=model.created_at,
            updated_at=model.updated_at,
            reviewer_id=model.reviewer_id,
            submitted_at=model.submitted_at,
            reviewed_at=model.reviewed_at,
            version=model.version,
            corrections=[_correction_entity(c) for c in corrections],
        )

    def save(self, request: ResearchProductRequest) -> None:
        model = self._session.get(ResearchProductRequestModel, request.id)
        if model is None:
            raise LookupError(f"Solicitud {request.id} no existe")
        _apply(model, request)
        self._sync_corrections(request)
        try:
            self._session.flush()
        except StaleDataError as error:
            raise ConcurrentModification(
                "La solicitud fue modificada por otra operación"
            ) from error
        request.version = model.version

    def _sync_corrections(self, request: ResearchProductRequest) -> None:
        stored = {
            c.id: c
            for c in self._session.scalars(
                select(RequestCorrectionModel).where(
                    RequestCorrectionModel.request_id == request.id
                )
            )
        }
        for correction in request.corrections:
            status_id = CORRECTION_STATUS_IDS[correction.status]
            existing = stored.get(correction.id)
            if existing is None:
                self._session.add(
                    RequestCorrectionModel(
                        id=correction.id,
                        request_id=correction.request_id,
                        requested_by=correction.requested_by,
                        description=correction.description,
                        status_id=status_id,
                        created_at=correction.created_at,
                        resolved_at=correction.resolved_at,
                    )
                )
            else:  # la descripción es histórica: solo cambian estado y fecha de resolución
                existing.status_id = status_id
                existing.resolved_at = correction.resolved_at
        self._session.flush()

    def search(
        self, scope: RequestScope, filters: RequestFilter, page: PageRequest
    ) -> Page[RequestSummary]:
        r = ResearchProductRequestModel
        query = (
            select(
                r,
                UserModel.first_name,
                UserModel.last_name,
                ProductTypeModel.id,
                ProductTypeModel.code,
                ProductTypeModel.name,
            )
            .join(UserModel, UserModel.id == r.mentor_id)
            .join(FormVersionModel, FormVersionModel.id == r.form_version_id)
            .join(ProductTypeModel, ProductTypeModel.id == FormVersionModel.product_type_id)
        )
        # 1) El alcance del actor es obligatorio e inviolable (ownership dentro de la consulta).
        if scope.mentor_id is not None:
            query = query.where(r.mentor_id == scope.mentor_id)
        if not scope.include_drafts:
            query = query.where(r.status_id != REQUEST_STATUS_IDS[RequestStatus.BORRADOR])
        if scope.product_ids is not None:  # un administrativo solo ve sus productos asignados
            query = query.where(FormVersionModel.product_type_id.in_(scope.product_ids))
        # 2) Filtros pedidos por el usuario.
        if filters.status is not None:
            query = query.where(r.status_id == REQUEST_STATUS_IDS[filters.status])
        if filters.product_type_id is not None:
            query = query.where(FormVersionModel.product_type_id == filters.product_type_id)
        if filters.mentor_id is not None:
            query = query.where(r.mentor_id == filters.mentor_id)
        if filters.date_from is not None:
            query = query.where(r.created_at >= datetime.combine(filters.date_from, time.min, UTC))
        if filters.date_to is not None:
            query = query.where(
                r.created_at < datetime.combine(filters.date_to + timedelta(days=1), time.min, UTC)
            )
        if filters.request_number and filters.request_number.strip():
            query = query.where(
                r.request_number.startswith(filters.request_number.strip().upper(), autoescape=True)
            )

        total = self._session.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = self._session.execute(
            query.order_by(r.created_at.desc(), r.id).limit(page.limit).offset(page.offset)
        ).all()
        items = tuple(
            RequestSummary(
                id=m.id,
                request_number=m.request_number,
                mentor_id=m.mentor_id,
                mentor_name=f"{first} {last}",
                product_type_id=type_id,
                product_type_code=code,
                product_type_name=name,
                form_version_id=m.form_version_id,
                status=REQUEST_STATUS_BY_ID[m.status_id],
                version=m.version,
                created_at=m.created_at,
                updated_at=m.updated_at,
                submitted_at=m.submitted_at,
                reviewed_at=m.reviewed_at,
            )
            for m, first, last, type_id, code, name in rows
        )
        return Page(items=items, total=total, page=page.page, page_size=page.page_size)
