from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.sql.expression import ColumnElement

from app.application.dto.forms import FormVersionSummary
from app.domain.enums.form_status import FormStatus
from app.domain.exceptions.errors import FormDraftExists
from app.domain.forms.definition import FormField, FormOption, FormSection, FormVersion
from app.infrastructure.database.catalog import (
    DOCUMENT_TYPE_BY_ID,
    DOCUMENT_TYPE_IDS,
    FIELD_TYPE_BY_ID,
    FIELD_TYPE_IDS,
    FORM_STATUS_BY_ID,
    FORM_STATUS_IDS,
)
from app.infrastructure.database.models.form import (
    FormFieldDocumentTypeModel,
    FormFieldModel,
    FormFieldOptionModel,
    FormSectionModel,
    FormVersionModel,
)

DRAFT_CONFLICTS = {"uq_form_versions_one_draft", "uq_form_versions_type_number"}


def _to_entity(model: FormVersionModel) -> FormVersion:
    return FormVersion(
        id=model.id,
        product_type_id=model.product_type_id,
        version_number=model.version_number,
        status=FORM_STATUS_BY_ID[model.status_id],
        created_by=model.created_by,
        created_at=model.created_at,
        published_at=model.published_at,
        retired_at=model.retired_at,
        sections=tuple(
            FormSection(
                id=section.id,
                title=section.title,
                description=section.description,
                fields=tuple(
                    FormField(
                        id=f.id,
                        key=f.key,
                        label=f.label,
                        type_code=FIELD_TYPE_BY_ID[f.field_type_id],
                        required_to_submit=f.required_to_submit,
                        help_text=f.help_text,
                        min_length=f.min_length,
                        max_length=f.max_length,
                        min_value=f.min_value,
                        max_value=f.max_value,
                        options=tuple(FormOption(o.value, o.label, o.id) for o in f.options),
                        allowed_types=tuple(
                            DOCUMENT_TYPE_BY_ID[d.document_type_id] for d in f.document_types
                        ),
                    )
                    for f in section.fields
                ),
            )
            for section in model.sections
        ),
    )


def _build_sections(version: FormVersion) -> list[FormSectionModel]:
    """Convierte la estructura del dominio en filas; la posición es el orden de la lista."""
    return [
        FormSectionModel(
            position=s_index,
            title=section.title,
            description=section.description,
            fields=[
                FormFieldModel(
                    position=f_index,
                    key=f.key,
                    label=f.label,
                    help_text=f.help_text,
                    field_type_id=FIELD_TYPE_IDS[f.type_code],
                    required_to_submit=f.required_to_submit,
                    min_length=f.min_length,
                    max_length=f.max_length,
                    min_value=f.min_value,
                    max_value=f.max_value,
                    options=[
                        FormFieldOptionModel(position=o_index, value=o.value, label=o.label)
                        for o_index, o in enumerate(f.options, start=1)
                    ],
                    document_types=[
                        FormFieldDocumentTypeModel(document_type_id=DOCUMENT_TYPE_IDS[t])
                        for t in f.allowed_types
                    ],
                )
                for f_index, f in enumerate(section.fields, start=1)
            ],
        )
        for s_index, section in enumerate(version.sections, start=1)
    ]


class SqlAlchemyFormRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # ---------------- lectura ----------------
    def get(self, version_id: int, *, for_update: bool = False) -> FormVersion | None:
        return self._one(FormVersionModel.id == version_id, for_update)

    def get_published(
        self, product_type_id: int, *, for_update: bool = False
    ) -> FormVersion | None:
        return self._one(
            (FormVersionModel.product_type_id == product_type_id)
            & (FormVersionModel.status_id == FORM_STATUS_IDS[FormStatus.PUBLICADA]),
            for_update,
        )

    def get_draft(self, product_type_id: int, *, for_update: bool = False) -> FormVersion | None:
        return self._one(
            (FormVersionModel.product_type_id == product_type_id)
            & (FormVersionModel.status_id == FORM_STATUS_IDS[FormStatus.BORRADOR]),
            for_update,
        )

    def list_versions(self, product_type_id: int) -> list[FormVersionSummary]:
        rows = self._session.scalars(
            select(FormVersionModel)
            .where(FormVersionModel.product_type_id == product_type_id)
            .order_by(FormVersionModel.version_number.desc())
        ).all()
        return [
            FormVersionSummary(
                id=r.id,
                version_number=r.version_number,
                status=FORM_STATUS_BY_ID[r.status_id],
                created_at=r.created_at,
                published_at=r.published_at,
                retired_at=r.retired_at,
            )
            for r in rows
        ]

    def next_version_number(self, product_type_id: int) -> int:
        latest = self._session.scalar(
            select(func.max(FormVersionModel.version_number)).where(
                FormVersionModel.product_type_id == product_type_id
            )
        )
        return (latest or 0) + 1

    # ---------------- escritura ----------------
    def add(self, version: FormVersion) -> FormVersion:
        model = FormVersionModel(
            product_type_id=version.product_type_id,
            version_number=version.version_number,
            status_id=FORM_STATUS_IDS[version.status],
            created_by=version.created_by,
            created_at=version.created_at,
            published_at=version.published_at,
            retired_at=version.retired_at,
            sections=_build_sections(version),
        )
        self._session.add(model)
        self._flush()
        return self._reload(model.id)

    def save(self, version: FormVersion) -> FormVersion:
        if version.id is None:
            raise LookupError("La versión aún no se ha guardado")
        model = self._load(FormVersionModel.id == version.id, for_update=False)
        if model is None:
            raise LookupError(f"Versión {version.id} no existe")
        was_draft = model.status_id == FORM_STATUS_IDS[FormStatus.BORRADOR]
        model.status_id = FORM_STATUS_IDS[version.status]
        model.published_at = version.published_at
        model.retired_at = version.retired_at
        if was_draft:  # también al publicar: el borrador se guarda con su última estructura
            # Un borrador se reemplaza completo: borrar y volver a insertar en dos pasos evita que
            # el INSERT (que el ORM ejecuta antes que los DELETE) choque con claves únicas.
            model.sections.clear()
            self._flush()
            model.sections.extend(_build_sections(version))
        self._flush()
        return self._reload(model.id)

    # ---------------- internos ----------------
    def _load(self, where: ColumnElement[bool], for_update: bool) -> FormVersionModel | None:
        query = (
            select(FormVersionModel)
            .where(where)
            .options(
                selectinload(FormVersionModel.sections)
                .selectinload(FormSectionModel.fields)
                .selectinload(FormFieldModel.options)
            )
            .options(
                selectinload(FormVersionModel.sections)
                .selectinload(FormSectionModel.fields)
                .selectinload(FormFieldModel.document_types)
            )
            .execution_options(populate_existing=True)
        )
        if for_update:
            query = query.with_for_update(of=FormVersionModel)
        return self._session.scalars(query).one_or_none()

    def _one(self, where: ColumnElement[bool], for_update: bool) -> FormVersion | None:
        model = self._load(where, for_update)
        return _to_entity(model) if model else None

    def _reload(self, version_id: int) -> FormVersion:
        model = self._load(FormVersionModel.id == version_id, for_update=False)
        assert model is not None
        return _to_entity(model)

    def _flush(self) -> None:
        try:
            self._session.flush()
        except IntegrityError as error:
            diag = getattr(error.orig, "diag", None)
            if getattr(diag, "constraint_name", None) in DRAFT_CONFLICTS:
                raise FormDraftExists(
                    "Ya existe un borrador de este formulario (o se creó a la vez otro)"
                ) from error
            raise
