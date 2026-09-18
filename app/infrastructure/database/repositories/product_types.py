from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.dto.page import Page, PageRequest
from app.domain.entities.product_type import ProductType
from app.domain.exceptions.errors import DuplicateProductType
from app.infrastructure.database.models.product_type import ProductTypeModel

UNIQUE_CONSTRAINTS = {"uq_product_types_code", "uq_product_types_folder_lower"}


def to_entity(model: ProductTypeModel) -> ProductType:
    return ProductType(
        id=model.id,
        code=model.code,
        name=model.name,
        description=model.description,
        folder_name=model.folder_name,
        is_active=model.is_active,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class SqlAlchemyProductTypeRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, product_type_id: int) -> ProductType | None:
        model = self._session.get(ProductTypeModel, product_type_id)
        return to_entity(model) if model else None

    def get_by_code(self, code: str) -> ProductType | None:
        model = self._session.scalars(
            select(ProductTypeModel).where(ProductTypeModel.code == code)
        ).one_or_none()
        return to_entity(model) if model else None

    def add(self, product_type: ProductType) -> None:
        model = ProductTypeModel(
            code=product_type.code,
            name=product_type.name,
            description=product_type.description,
            folder_name=product_type.folder_name,
            is_active=product_type.is_active,
            created_at=product_type.created_at,
            updated_at=product_type.updated_at,
        )
        self._session.add(model)
        try:
            self._session.flush()
        except IntegrityError as error:
            diag = getattr(error.orig, "diag", None)
            if getattr(diag, "constraint_name", None) in UNIQUE_CONSTRAINTS:
                raise DuplicateProductType(
                    "Ya existe un producto con ese código o esa carpeta de soportes"
                ) from error
            raise
        product_type.id = model.id

    def save(self, product_type: ProductType) -> None:
        if product_type.id is None:
            raise LookupError("El tipo de producto aún no se ha guardado")
        model = self._session.get(ProductTypeModel, product_type.id)
        if model is None:
            raise LookupError(f"Tipo de producto {product_type.id} no existe")
        model.name = product_type.name
        model.description = product_type.description
        model.is_active = product_type.is_active
        model.updated_at = product_type.updated_at
        self._session.flush()

    def list(self, only_active: bool, page: PageRequest) -> Page[ProductType]:
        query = select(ProductTypeModel)
        if only_active:
            query = query.where(ProductTypeModel.is_active.is_(True))
        total = self._session.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = self._session.scalars(
            query.order_by(ProductTypeModel.name, ProductTypeModel.id)
            .limit(page.limit)
            .offset(page.offset)
        ).all()
        return Page(
            items=tuple(to_entity(r) for r in rows),
            total=total,
            page=page.page,
            page_size=page.page_size,
        )
