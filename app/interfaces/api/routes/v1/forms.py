from fastapi import APIRouter, status

from app.application.commands.forms import (
    CreateProductTypeCommand,
    ReplaceFormDraftCommand,
    UpdateProductTypeCommand,
)
from app.interfaces.api.dependencies import ActorDep, ContainerDep, ContextDep
from app.interfaces.api.schemas.common import PageNumber, PageOut, PageSize, page_request
from app.interfaces.api.schemas.forms import (
    FormDocumentIn,
    FormVersionOut,
    FormVersionSummaryOut,
    ProductTypeCreateIn,
    ProductTypeOut,
    ProductTypeUpdateIn,
)

router = APIRouter(tags=["products and forms"])


# ---------------- productos ----------------
@router.get(
    "/product-types",
    response_model=PageOut[ProductTypeOut],
    summary="Productos disponibles (quien gestiona formularios ve también los inactivos)",
)
def list_product_types(
    actor: ActorDep, container: ContainerDep, page: PageNumber = 1, page_size: PageSize = 20
) -> PageOut[ProductTypeOut]:
    result = container.list_product_types().execute(actor, page_request(page, page_size))
    return PageOut.of(result, [ProductTypeOut.of(p) for p in result.items])


@router.post(
    "/product-types",
    response_model=ProductTypeOut,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un producto nuevo (deja listo su primer borrador de formulario)",
)
def create_product_type(
    body: ProductTypeCreateIn, actor: ActorDep, container: ContainerDep, ctx: ContextDep
) -> ProductTypeOut:
    product, _ = container.create_product_type().execute(
        actor,
        CreateProductTypeCommand(body.code, body.name, body.description, body.folder_name),
        ctx,
    )
    return ProductTypeOut.of(product)


@router.patch(
    "/product-types/{product_type_id}", response_model=ProductTypeOut, summary="Editar un producto"
)
def update_product_type(
    product_type_id: int,
    body: ProductTypeUpdateIn,
    actor: ActorDep,
    container: ContainerDep,
    ctx: ContextDep,
) -> ProductTypeOut:
    product = container.update_product_type().execute(
        actor,
        UpdateProductTypeCommand(product_type_id, body.name, body.description, body.is_active),
        ctx,
    )
    return ProductTypeOut.of(product)


# ---------------- formularios ----------------
@router.get(
    "/product-types/{product_type_id}/form",
    response_model=FormVersionOut,
    summary="Formulario vigente (publicado) de un producto",
)
def published_form(
    product_type_id: int, actor: ActorDep, container: ContainerDep
) -> FormVersionOut:
    return FormVersionOut.of(container.get_published_form().execute(actor, product_type_id))


@router.get(
    "/product-types/{product_type_id}/form-versions",
    response_model=list[FormVersionSummaryOut],
    summary="Versiones de formulario de un producto",
)
def list_form_versions(
    product_type_id: int, actor: ActorDep, container: ContainerDep
) -> list[FormVersionSummaryOut]:
    return [
        FormVersionSummaryOut.of(v)
        for v in container.list_form_versions().execute(actor, product_type_id)
    ]


@router.post(
    "/product-types/{product_type_id}/form-versions",
    response_model=FormVersionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Abrir un borrador (copia de la versión publicada)",
)
def create_draft(
    product_type_id: int, actor: ActorDep, container: ContainerDep, ctx: ContextDep
) -> FormVersionOut:
    return FormVersionOut.of(container.create_form_draft().execute(actor, product_type_id, ctx))


@router.get(
    "/form-versions/{version_id}", response_model=FormVersionOut, summary="Ver una versión completa"
)
def get_form_version(version_id: int, actor: ActorDep, container: ContainerDep) -> FormVersionOut:
    return FormVersionOut.of(container.get_form_version().execute(actor, version_id))


@router.put(
    "/form-versions/{version_id}",
    response_model=FormVersionOut,
    summary="Guardar el borrador completo (secciones, campos y opciones)",
)
def replace_draft(
    version_id: int,
    body: FormDocumentIn,
    actor: ActorDep,
    container: ContainerDep,
    ctx: ContextDep,
) -> FormVersionOut:
    saved = container.replace_form_draft().execute(
        actor, ReplaceFormDraftCommand(version_id, body.to_sections()), ctx
    )
    return FormVersionOut.of(saved)


@router.post(
    "/form-versions/{version_id}/publish",
    response_model=FormVersionOut,
    summary="Publicar el borrador (retira la versión publicada anterior)",
)
def publish(
    version_id: int, actor: ActorDep, container: ContainerDep, ctx: ContextDep
) -> FormVersionOut:
    return FormVersionOut.of(container.publish_form().execute(actor, version_id, ctx))
