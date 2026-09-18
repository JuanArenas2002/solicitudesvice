from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.application.dto.forms import FormVersionSummary
from app.domain.entities.product_type import ProductType
from app.domain.enums.form_status import FormStatus
from app.domain.forms.definition import FormField, FormVersion, SectionInput
from app.interfaces.api.schemas.common import Input


# ---------------- producto ----------------
class ProductTypeCreateIn(Input):
    code: str = Field(max_length=30, description="Código único en mayúsculas, p. ej. LIBRO")
    name: str = Field(max_length=120)
    description: str | None = Field(default=None, max_length=500)
    folder_name: str | None = Field(
        default=None,
        max_length=50,
        description="Carpeta de soportes (p. ej. Articulos). No se puede cambiar después.",
    )


class ProductTypeUpdateIn(Input):
    name: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None


class ProductTypeOut(BaseModel):
    id: int
    code: str
    name: str
    description: str | None
    folder_name: str
    is_active: bool

    @classmethod
    def of(cls, product: ProductType) -> "ProductTypeOut":
        assert product.id is not None
        return cls(
            id=product.id,
            code=product.code,
            name=product.name,
            description=product.description,
            folder_name=product.folder_name,
            is_active=product.is_active,
        )


# ---------------- documento del formulario (entrada del constructor) ----------------
class OptionIn(Input):
    value: str = Field(max_length=100)
    label: str = Field(max_length=200)


class FieldIn(Input):
    key: str = Field(max_length=60, description="Identificador estable: minúsculas, dígitos y _")
    label: str = Field(max_length=200)
    type: str = Field(max_length=30, description="TEXT, INTEGER, DATE, DOI, SINGLE_SELECT, ...")
    required_to_submit: bool = False
    help_text: str | None = Field(default=None, max_length=500)
    min_length: int | None = None
    max_length: int | None = None
    min_value: int | float | str | None = None
    max_value: int | float | str | None = None
    options: list[OptionIn] = Field(default_factory=list, max_length=100)
    allowed_types: list[str] = Field(
        default_factory=list,
        max_length=20,
        description="Solo para SUPPORT: extensiones admitidas (pdf, docx, png...)",
    )


class SectionIn(Input):
    title: str = Field(max_length=200)
    description: str | None = Field(default=None, max_length=500)
    fields: list[FieldIn] = Field(default_factory=list, max_length=200)


class FormDocumentIn(Input):
    sections: list[SectionIn] = Field(max_length=30)

    def to_sections(self) -> list[SectionInput]:
        """Convierte al formato que valida el dominio (que es quien manda)."""
        return [section.model_dump() for section in self.sections]  # type: ignore[misc]


# ---------------- formulario (salida) ----------------
class OptionOut(BaseModel):
    id: int | None
    value: str
    label: str


class FieldOut(BaseModel):
    id: int | None
    key: str
    label: str
    type: str
    required_to_submit: bool
    help_text: str | None
    min_length: int | None
    max_length: int | None
    min_value: Decimal | None
    max_value: Decimal | None
    options: list[OptionOut]
    allowed_types: list[str]

    @classmethod
    def of(cls, f: FormField) -> "FieldOut":
        return cls(
            id=f.id,
            key=f.key,
            label=f.label,
            type=f.type_code,
            required_to_submit=f.required_to_submit,
            help_text=f.help_text,
            min_length=f.min_length,
            max_length=f.max_length,
            min_value=f.min_value,
            max_value=f.max_value,
            options=[OptionOut(id=o.id, value=o.value, label=o.label) for o in f.options],
            allowed_types=list(f.allowed_types),
        )


class SectionOut(BaseModel):
    id: int | None
    title: str
    description: str | None
    fields: list[FieldOut]


class FormVersionOut(BaseModel):
    id: int | None
    product_type_id: int
    version_number: int
    status: FormStatus
    created_at: datetime
    published_at: datetime | None
    retired_at: datetime | None
    sections: list[SectionOut]

    @classmethod
    def of(cls, version: FormVersion) -> "FormVersionOut":
        return cls(
            id=version.id,
            product_type_id=version.product_type_id,
            version_number=version.version_number,
            status=version.status,
            created_at=version.created_at,
            published_at=version.published_at,
            retired_at=version.retired_at,
            sections=[
                SectionOut(
                    id=s.id,
                    title=s.title,
                    description=s.description,
                    fields=[FieldOut.of(f) for f in s.fields],
                )
                for s in version.sections
            ],
        )


class FormVersionSummaryOut(BaseModel):
    id: int
    version_number: int
    status: FormStatus
    created_at: datetime
    published_at: datetime | None
    retired_at: datetime | None

    @classmethod
    def of(cls, s: FormVersionSummary) -> "FormVersionSummaryOut":
        return cls(
            id=s.id,
            version_number=s.version_number,
            status=s.status,
            created_at=s.created_at,
            published_at=s.published_at,
            retired_at=s.retired_at,
        )
