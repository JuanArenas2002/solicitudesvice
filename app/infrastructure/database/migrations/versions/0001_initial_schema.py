"""Esquema inicial (normalizado)

Revision ID: 0001
Revises:
Create Date: 2026-09-18

Escrita a mano con expresiones SQLAlchemy y operaciones de Alembic (sin SQL textual). Es una
instantánea congelada: no importa nada de app.domain para que cambios futuros del dominio no
alteren migraciones pasadas. Los tests verifican que coincide con los modelos y con el catálogo.

Catálogos (roles, estados, tipos, acciones) = tablas con PK SMALLINT sembradas aquí con ids fijos.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.expression import ColumnClause

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# ---- catálogos (ids fijos e inmutables) ----
ROLES = [(1, "ADMIN"), (2, "ADMINISTRATIVO"), (3, "MENTOR")]
REQUEST_STATUSES = [
    (1, "BORRADOR"),
    (2, "ENVIADA"),
    (3, "EN_REVISION"),
    (4, "CORRECCION_SOLICITADA"),
    (5, "REENVIADA"),
    (6, "APROBADA"),
    (7, "RECHAZADA"),
]
CORRECTION_STATUSES = [(1, "ABIERTA"), (2, "RESUELTA")]
FORM_STATUSES = [(1, "BORRADOR"), (2, "PUBLICADA"), (3, "RETIRADA")]
VALUE_KINDS = [
    (1, "TEXT"),
    (2, "NUMBER"),
    (3, "DATE"),
    (4, "BOOLEAN"),
    (5, "OPTION"),
    (6, "FILE"),
]
DOCUMENT_TYPES = [
    (1, "pdf"),
    (2, "png"),
    (3, "jpg"),
    (4, "jpeg"),
    (5, "doc"),
    (6, "docx"),
    (7, "xls"),
    (8, "xlsx"),
    (9, "ppt"),
    (10, "pptx"),
    (11, "zip"),
]
FIELD_TYPES = [  # (id, código, id de la clase de valor)
    (1, "TEXT", 1),
    (2, "LONG_TEXT", 1),
    (3, "INTEGER", 2),
    (4, "DECIMAL", 2),
    (5, "DATE", 3),
    (6, "BOOLEAN", 4),
    (7, "SINGLE_SELECT", 5),
    (8, "MULTI_SELECT", 5),
    (9, "URL", 1),
    (10, "DOI", 1),
    (11, "ISSN", 1),
    (12, "EMAIL", 1),
    (13, "CEDULA", 1),
    (14, "SUPPORT", 6),
]
AUDIT_CATEGORIES = [(1, "SECURITY"), (2, "REQUESTS"), (3, "CONFIGURATION")]
AUDIT_ACTIONS = [
    (1, "LOGIN_SUCCEEDED", 1, "session"),
    (2, "LOGIN_FAILED", 1, "session"),
    (3, "LOGOUT", 1, "session"),
    (4, "SESSION_REVOKED", 1, "session"),
    (5, "REFRESH_REUSE_DETECTED", 1, "session"),
    (6, "PASSWORD_CHANGED", 1, "user"),
    (7, "PASSWORD_RESET", 1, "user"),
    (8, "USER_CREATED", 1, "user"),
    (9, "USER_UPDATED", 1, "user"),
    (10, "USER_ACTIVATED", 1, "user"),
    (11, "USER_DEACTIVATED", 1, "user"),
    (12, "REQUEST_CREATED", 2, "request"),
    (13, "REQUEST_UPDATED", 2, "request"),
    (14, "REQUEST_SUBMITTED", 2, "request"),
    (15, "REVIEW_STARTED", 2, "request"),
    (16, "CORRECTION_REQUESTED", 2, "request"),
    (17, "REQUEST_RESUBMITTED", 2, "request"),
    (18, "REQUEST_APPROVED", 2, "request"),
    (19, "REQUEST_REJECTED", 2, "request"),
    (20, "ATTACHMENT_UPLOADED", 2, "attachment"),
    (21, "ATTACHMENT_DELETED", 2, "attachment"),
    (22, "PRODUCT_TYPE_CREATED", 3, "product_type"),
    (23, "PRODUCT_TYPE_UPDATED", 3, "product_type"),
    (24, "FORM_DRAFT_CREATED", 3, "form_version"),
    (25, "FORM_DRAFT_SAVED", 3, "form_version"),
    (26, "FORM_PUBLISHED", 3, "form_version"),
    (27, "USER_PRODUCTS_ASSIGNED", 3, "user"),
    (28, "REQUEST_STATUS_CHANGED", 2, "request"),
]

# ids de estado usados en los CHECK
BORRADOR, ENVIADA = 1, 2
CORRECCION_SOLICITADA, REENVIADA, APROBADA, RECHAZADA = 4, 5, 6, 7
CORRECTION_ABIERTA, CORRECTION_RESUELTA = 1, 2
FORM_BORRADOR, FORM_PUBLICADA, FORM_RETIRADA = 1, 2, 3
KIND_TEXT, KIND_NUMBER, KIND_DATE, KIND_BOOLEAN, KIND_OPTION = 1, 2, 3, 4, 5
TYPE_INTEGER, TYPE_SINGLE_SELECT, TYPE_URL, TYPE_DOI, TYPE_ISSN, TYPE_EMAIL = 3, 7, 9, 10, 11, 12
TYPE_CEDULA = 13
TYPE_SUPPORT = 14

DOI = "^10[.][0-9]{4,9}/[^ ]+$"
ISSN = "^[0-9]{4}-[0-9]{3}[0-9X]$"
URL = "^https?://[^ ]+$"
EMAIL = "^[^@ ]+@[^@ ]+[.][^@ ]+$"
KEY = "^[a-z][a-z0-9_]{0,59}$"
PRODUCT_CODE = "^[A-Z][A-Z0-9_]{1,29}$"
FOLDER_NAME = "^[A-Za-z0-9][A-Za-z0-9_-]{0,49}$"
CEDULA = "^[0-9]{5,15}$"
REQUEST_NUMBER = "^SOL-[0-9]{4}-[0-9]{6}$"


def _uuid(name: str, *, nullable: bool = False) -> sa.Column[uuid.UUID]:
    return sa.Column(name, sa.Uuid(), nullable=nullable)


def _smallint(name: str, *, nullable: bool = False) -> sa.Column[int]:
    return sa.Column(name, sa.SmallInteger(), nullable=nullable)


def _ts(name: str, *, nullable: bool = False, now: bool = False) -> sa.Column[datetime]:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        server_default=sa.func.now() if now else None,
        nullable=nullable,
    )


def _pk(table: str, column: str = "id") -> sa.PrimaryKeyConstraint:
    return sa.PrimaryKeyConstraint(column, name=op.f(f"pk_{table}"))


def _fk(table: str, column: str, ref_table: str, ref_column: str = "id") -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column],
        [f"{ref_table}.{ref_column}"],
        name=op.f(f"fk_{table}_{column}_{ref_table}"),
        ondelete="RESTRICT",
    )


def _ck(table: str, name: str, expression: sa.ColumnElement[bool]) -> sa.CheckConstraint:
    return sa.CheckConstraint(expression, name=op.f(f"ck_{table}_{name}"))


def _not_blank(table: str, column: str) -> sa.CheckConstraint:
    return _ck(table, f"{column}_not_blank", sa.func.length(sa.func.trim(sa.column(column))) > 0)


def _lookup(name: str, rows: Sequence[tuple[int, str]]) -> None:
    """Crea un catálogo (id SMALLINT fijo + código único) y lo siembra con bulk_insert."""
    op.create_table(
        name,
        sa.Column("id", sa.SmallInteger(), autoincrement=False, nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        _pk(name),
        sa.UniqueConstraint("code", name=op.f(f"uq_{name}_code")),
    )
    table = sa.table(name, sa.column("id", sa.SmallInteger()), sa.column("code", sa.String()))
    op.bulk_insert(table, [{"id": i, "code": code} for i, code in rows])


def _int(name: str, *, nullable: bool = False) -> sa.Column[int]:
    return sa.Column(name, sa.Integer(), nullable=nullable)


def _fk_composite(
    table: str,
    name_column: str,
    columns: list[str],
    ref_table: str,
    ref_columns: list[str],
) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        columns,
        [f"{ref_table}.{c}" for c in ref_columns],
        name=op.f(f"fk_{table}_{name_column}_{ref_table}"),
        ondelete="RESTRICT",
    )


def upgrade() -> None:
    for name, rows in (
        ("roles", ROLES),
        ("request_statuses", REQUEST_STATUSES),
        ("correction_statuses", CORRECTION_STATUSES),
        ("form_statuses", FORM_STATUSES),
        ("value_kinds", VALUE_KINDS),
        ("document_types", DOCUMENT_TYPES),
        ("audit_categories", AUDIT_CATEGORIES),
    ):
        _lookup(name, rows)

    op.create_table(
        "field_types",
        _smallint("value_kind_id"),
        sa.Column("id", sa.SmallInteger(), autoincrement=False, nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        _pk("field_types"),
        _fk("field_types", "value_kind_id", "value_kinds"),
        sa.UniqueConstraint("code", name=op.f("uq_field_types_code")),
        sa.UniqueConstraint("id", "value_kind_id", name="uq_field_types_id_value_kind"),
    )
    op.bulk_insert(
        sa.table(
            "field_types",
            sa.column("id", sa.SmallInteger()),
            sa.column("code", sa.String()),
            sa.column("value_kind_id", sa.SmallInteger()),
        ),
        [{"id": i, "code": code, "value_kind_id": kind} for i, code, kind in FIELD_TYPES],
    )

    op.create_table(
        "audit_actions",
        sa.Column("category_id", sa.SmallInteger(), nullable=False),
        sa.Column("entity_type", sa.String(30), nullable=False),
        sa.Column("id", sa.SmallInteger(), autoincrement=False, nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        _pk("audit_actions"),
        _fk("audit_actions", "category_id", "audit_categories"),
        sa.UniqueConstraint("code", name=op.f("uq_audit_actions_code")),
    )
    op.bulk_insert(
        sa.table(
            "audit_actions",
            sa.column("id", sa.SmallInteger()),
            sa.column("code", sa.String()),
            sa.column("category_id", sa.SmallInteger()),
            sa.column("entity_type", sa.String()),
        ),
        [
            {"id": i, "code": code, "category_id": cat, "entity_type": entity}
            for i, code, cat, entity in AUDIT_ACTIONS
        ],
    )

    op.create_table(
        "request_counters",
        sa.Column("year", sa.SmallInteger(), autoincrement=False, nullable=False),
        sa.Column("last_value", sa.Integer(), nullable=False),
        _pk("request_counters", "year"),
        _ck("request_counters", "last_value_range", sa.column("last_value").between(0, 999999)),
    )

    op.create_table(
        "users",
        _uuid("id"),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        _smallint("role_id"),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        _ts("created_at", now=True),
        _ts("updated_at", now=True),
        _ts("last_login_at", nullable=True),
        _pk("users"),
        _ck("users", "email_lowercase", sa.column("email") == sa.func.lower(sa.column("email"))),
        _not_blank("users", "first_name"),
        _not_blank("users", "last_name"),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
        _fk("users", "role_id", "roles"),
    )

    # ---------------- productos y formularios (dinámicos) ----------------
    op.create_table(
        "product_types",
        sa.Column("id", sa.Integer(), sa.Identity(always=True)),
        sa.Column("code", sa.String(30), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("folder_name", sa.String(50), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        _ts("created_at", now=True),
        _ts("updated_at", now=True),
        _pk("product_types"),
        _ck("product_types", "code_format", sa.column("code").regexp_match(PRODUCT_CODE)),
        _not_blank("product_types", "name"),
        _ck(
            "product_types",
            "folder_name_format",
            sa.column("folder_name").regexp_match(FOLDER_NAME),
        ),
        sa.UniqueConstraint("code", name=op.f("uq_product_types_code")),
    )
    op.create_index(
        "uq_product_types_folder_lower",
        "product_types",
        [sa.func.lower(sa.column("folder_name"))],
        unique=True,
    )

    form_status: ColumnClause[int] = sa.column("status_id")
    published_at: ColumnClause[datetime] = sa.column("published_at")
    retired_at: ColumnClause[datetime] = sa.column("retired_at")
    op.create_table(
        "form_versions",
        sa.Column("id", sa.Integer(), sa.Identity(always=True)),
        _int("product_type_id"),
        _int("version_number"),
        _smallint("status_id"),
        _uuid("created_by", nullable=True),
        _ts("created_at", now=True),
        _ts("published_at", nullable=True),
        _ts("retired_at", nullable=True),
        _pk("form_versions"),
        _ck("form_versions", "version_number_positive", sa.column("version_number") >= 1),
        _ck(
            "form_versions",
            "dates_match_status",
            sa.or_(
                sa.and_(form_status == FORM_BORRADOR, published_at.is_(None), retired_at.is_(None)),
                sa.and_(
                    form_status == FORM_PUBLICADA, published_at.is_not(None), retired_at.is_(None)
                ),
                sa.and_(
                    form_status == FORM_RETIRADA,
                    published_at.is_not(None),
                    retired_at.is_not(None),
                    retired_at >= published_at,
                ),
            ),
        ),
        sa.UniqueConstraint(
            "product_type_id", "version_number", name="uq_form_versions_type_number"
        ),
        _fk("form_versions", "product_type_id", "product_types"),
        _fk("form_versions", "status_id", "form_statuses"),
        _fk("form_versions", "created_by", "users"),
    )
    op.create_index(
        "uq_form_versions_one_draft",
        "form_versions",
        ["product_type_id"],
        unique=True,
        postgresql_where=form_status == FORM_BORRADOR,
    )
    op.create_index(
        "uq_form_versions_one_published",
        "form_versions",
        ["product_type_id"],
        unique=True,
        postgresql_where=form_status == FORM_PUBLICADA,
    )

    op.create_table(
        "form_sections",
        sa.Column("id", sa.Integer(), sa.Identity(always=True)),
        _int("form_version_id"),
        _smallint("position"),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        _pk("form_sections"),
        _ck("form_sections", "position_positive", sa.column("position") >= 1),
        _not_blank("form_sections", "title"),
        sa.UniqueConstraint(
            "form_version_id",
            "position",
            name="uq_form_sections_version_position",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.UniqueConstraint("id", "form_version_id", name="uq_form_sections_id_version"),
        _fk("form_sections", "form_version_id", "form_versions"),
    )

    op.create_table(
        "form_fields",
        sa.Column("id", sa.Integer(), sa.Identity(always=True)),
        _int("form_version_id"),
        _int("section_id"),
        _smallint("position"),
        sa.Column("key", sa.String(60), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("help_text", sa.String(500), nullable=True),
        _smallint("field_type_id"),
        sa.Column("required_to_submit", sa.Boolean(), server_default=sa.false(), nullable=False),
        _int("min_length", nullable=True),
        _int("max_length", nullable=True),
        sa.Column("min_value", sa.Numeric(20, 6), nullable=True),
        sa.Column("max_value", sa.Numeric(20, 6), nullable=True),
        _pk("form_fields"),
        sa.ForeignKeyConstraint(
            ["section_id", "form_version_id"],
            ["form_sections.id", "form_sections.form_version_id"],
            name=op.f("fk_form_fields_section_id_form_sections"),
            ondelete="RESTRICT",
        ),
        _ck("form_fields", "key_format", sa.column("key").regexp_match(KEY)),
        _ck("form_fields", "position_positive", sa.column("position") >= 1),
        _not_blank("form_fields", "label"),
        _ck("form_fields", "min_length_non_negative", sa.column("min_length") >= 0),
        _ck(
            "form_fields",
            "length_range_valid",
            sa.or_(
                sa.column("max_length").is_(None),
                sa.and_(
                    sa.column("max_length") >= 0,
                    sa.or_(
                        sa.column("min_length").is_(None),
                        sa.column("max_length") >= sa.column("min_length"),
                    ),
                ),
            ),
        ),
        _ck(
            "form_fields",
            "value_range_valid",
            sa.or_(
                sa.column("min_value").is_(None),
                sa.column("max_value").is_(None),
                sa.column("max_value") >= sa.column("min_value"),
            ),
        ),
        sa.UniqueConstraint("form_version_id", "key", name="uq_form_fields_version_key"),
        sa.UniqueConstraint(
            "section_id",
            "position",
            name="uq_form_fields_section_position",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.UniqueConstraint(
            "id", "form_version_id", "field_type_id", name="uq_form_fields_id_version_type"
        ),
        _fk("form_fields", "field_type_id", "field_types"),
    )

    op.create_table(
        "form_field_options",
        sa.Column("id", sa.Integer(), sa.Identity(always=True)),
        _int("field_id"),
        _smallint("position"),
        sa.Column("value", sa.String(100), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        _pk("form_field_options"),
        _ck("form_field_options", "position_positive", sa.column("position") >= 1),
        _not_blank("form_field_options", "value"),
        _not_blank("form_field_options", "label"),
        sa.UniqueConstraint("field_id", "value", name="uq_form_field_options_field_value"),
        sa.UniqueConstraint(
            "field_id",
            "position",
            name="uq_form_field_options_field_position",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.UniqueConstraint("id", "field_id", name="uq_form_field_options_id_field"),
        _fk("form_field_options", "field_id", "form_fields"),
    )

    op.create_table(
        "form_field_document_types",
        _int("field_id"),
        _smallint("document_type_id"),
        sa.PrimaryKeyConstraint(
            "field_id", "document_type_id", name=op.f("pk_form_field_document_types")
        ),
        _fk("form_field_document_types", "field_id", "form_fields"),
        _fk("form_field_document_types", "document_type_id", "document_types"),
    )

    # ---------------- auditoría y sesiones ----------------
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True)),
        _ts("occurred_at", now=True),
        _uuid("actor_id", nullable=True),
        _smallint("action_id"),
        _uuid("entity_id", nullable=True),
        sa.Column("correlation_id", sa.String(64), nullable=True),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("detail", postgresql.JSONB(), nullable=False),
        _pk("audit_logs"),
        _fk("audit_logs", "actor_id", "users"),
        _fk("audit_logs", "action_id", "audit_actions"),
    )
    entity_id: ColumnClause[uuid.UUID] = sa.column("entity_id")
    actor_id: ColumnClause[uuid.UUID] = sa.column("actor_id")
    op.create_index("ix_audit_logs_action", "audit_logs", ["action_id", "occurred_at"])
    op.create_index(
        "ix_audit_logs_actor",
        "audit_logs",
        ["actor_id", "occurred_at"],
        postgresql_where=actor_id.is_not(None),
    )
    op.create_index(
        "ix_audit_logs_entity",
        "audit_logs",
        ["entity_id", "occurred_at"],
        postgresql_where=entity_id.is_not(None),
    )
    op.create_index(
        "ix_audit_logs_occurred_at", "audit_logs", ["occurred_at"], postgresql_using="brin"
    )

    revoked_at: ColumnClause[datetime] = sa.column("revoked_at")
    op.create_table(
        "auth_sessions",
        _uuid("id"),
        _uuid("user_id"),
        _ts("created_at", now=True),
        _ts("expires_at"),
        _ts("revoked_at", nullable=True),
        sa.Column("revoked_reason", sa.String(50), nullable=True),
        _pk("auth_sessions"),
        _ck(
            "auth_sessions",
            "revocation_consistent",
            sa.or_(
                sa.and_(revoked_at.is_(None), sa.column("revoked_reason").is_(None)),
                sa.and_(revoked_at.is_not(None), sa.column("revoked_reason").is_not(None)),
            ),
        ),
        _fk("auth_sessions", "user_id", "users"),
    )
    op.create_index(
        "ix_auth_sessions_user_active",
        "auth_sessions",
        ["user_id"],
        postgresql_where=revoked_at.is_(None),
    )

    op.create_table(
        "refresh_tokens",
        _uuid("id"),
        _uuid("session_id"),
        sa.Column("token_hash", sa.String(64), nullable=False),
        _ts("created_at", now=True),
        _ts("expires_at"),
        _ts("used_at", nullable=True),
        _pk("refresh_tokens"),
        _ck(
            "refresh_tokens",
            "token_hash_sha256",
            sa.column("token_hash").regexp_match("^[0-9a-f]{64}$"),
        ),
        _fk("refresh_tokens", "session_id", "auth_sessions"),
        sa.UniqueConstraint("token_hash", name=op.f("uq_refresh_tokens_token_hash")),
    )
    op.create_index("ix_refresh_tokens_session_id", "refresh_tokens", ["session_id"])

    # ---------------- solicitudes ----------------
    status: ColumnClause[int] = sa.column("status_id")
    unreviewed = [BORRADOR, ENVIADA]
    review_round_closed = [CORRECCION_SOLICITADA, REENVIADA, APROBADA, RECHAZADA]
    op.create_table(
        "research_product_requests",
        _uuid("id"),
        sa.Column("request_number", sa.String(15), nullable=False),
        _uuid("mentor_id"),
        _int("form_version_id"),
        _smallint("status_id"),
        _uuid("reviewer_id", nullable=True),
        _ts("submitted_at", nullable=True),
        _ts("reviewed_at", nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        _ts("created_at", now=True),
        _ts("updated_at", now=True),
        _pk("research_product_requests"),
        _ck(
            "research_product_requests",
            "request_number_format",
            sa.column("request_number").regexp_match(REQUEST_NUMBER),
        ),
        _ck(
            "research_product_requests",
            "submitted_at_matches_status",
            sa.or_(
                sa.and_(status == BORRADOR, sa.column("submitted_at").is_(None)),
                sa.and_(status != BORRADOR, sa.column("submitted_at").is_not(None)),
            ),
        ),
        _ck(
            "research_product_requests",
            "reviewer_matches_status",
            sa.or_(
                sa.and_(status.in_(unreviewed), sa.column("reviewer_id").is_(None)),
                sa.and_(status.not_in(unreviewed), sa.column("reviewer_id").is_not(None)),
            ),
        ),
        _ck(
            "research_product_requests",
            "reviewed_at_required",
            sa.or_(status.not_in(review_round_closed), sa.column("reviewed_at").is_not(None)),
        ),
        _ck("research_product_requests", "version_positive", sa.column("version") >= 1),
        sa.UniqueConstraint(
            "request_number", name=op.f("uq_research_product_requests_request_number")
        ),
        sa.UniqueConstraint("id", "form_version_id", name="uq_requests_id_form_version"),
        _fk("research_product_requests", "mentor_id", "users"),
        _fk("research_product_requests", "form_version_id", "form_versions"),
        _fk("research_product_requests", "status_id", "request_statuses"),
        _fk("research_product_requests", "reviewer_id", "users"),
    )
    op.create_index("ix_requests_created_at", "research_product_requests", ["created_at"])
    op.create_index("ix_requests_form_version", "research_product_requests", ["form_version_id"])
    op.create_index(
        "ix_requests_mentor_created", "research_product_requests", ["mentor_id", "created_at"]
    )
    op.create_index(
        "ix_requests_status_submitted", "research_product_requests", ["status_id", "submitted_at"]
    )

    kind: ColumnClause[int] = sa.column("value_kind_id")
    field_type: ColumnClause[int] = sa.column("field_type_id")
    text: ColumnClause[str] = sa.column("value_text")
    number: ColumnClause[int] = sa.column("value_number")
    date_: ColumnClause[datetime] = sa.column("value_date")
    boolean: ColumnClause[bool] = sa.column("value_boolean")
    option: ColumnClause[int] = sa.column("option_id")
    values: dict[str, ColumnClause[Any]] = {
        "text": text,
        "number": number,
        "date": date_,
        "boolean": boolean,
        "option": option,
    }

    def only(kept: str) -> sa.ColumnElement[bool]:
        return sa.and_(*(c.is_not(None) if n == kept else c.is_(None) for n, c in values.items()))

    def format_check(type_id: int, condition: sa.ColumnElement[bool]) -> sa.ColumnElement[bool]:
        return sa.or_(field_type != type_id, condition)

    op.create_table(
        "request_answers",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True)),
        _uuid("request_id"),
        _int("form_version_id"),
        _int("field_id"),
        _smallint("field_type_id"),
        _smallint("value_kind_id"),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("value_number", sa.Numeric(20, 6), nullable=True),
        sa.Column("value_date", sa.Date(), nullable=True),
        sa.Column("value_boolean", sa.Boolean(), nullable=True),
        _int("option_id", nullable=True),
        _pk("request_answers"),
        _fk_composite(
            "request_answers",
            "request_id",
            ["request_id", "form_version_id"],
            "research_product_requests",
            ["id", "form_version_id"],
        ),
        _fk_composite(
            "request_answers",
            "field_id",
            ["field_id", "form_version_id", "field_type_id"],
            "form_fields",
            ["id", "form_version_id", "field_type_id"],
        ),
        _fk_composite(
            "request_answers",
            "field_type_id",
            ["field_type_id", "value_kind_id"],
            "field_types",
            ["id", "value_kind_id"],
        ),
        _fk_composite(
            "request_answers",
            "option_id",
            ["option_id", "field_id"],
            "form_field_options",
            ["id", "field_id"],
        ),
        _ck(
            "request_answers",
            "value_matches_kind",
            sa.or_(
                sa.and_(kind == KIND_TEXT, only("text")),
                sa.and_(kind == KIND_NUMBER, only("number")),
                sa.and_(kind == KIND_DATE, only("date")),
                sa.and_(kind == KIND_BOOLEAN, only("boolean")),
                sa.and_(kind == KIND_OPTION, only("option")),
            ),
        ),
        _ck("request_answers", "text_not_blank", sa.func.length(sa.func.trim(text)) > 0),
        _ck("request_answers", "text_max_length", sa.func.length(text) <= 10000),
        _ck("request_answers", "doi_format", format_check(TYPE_DOI, text.regexp_match(DOI))),
        _ck("request_answers", "issn_format", format_check(TYPE_ISSN, text.regexp_match(ISSN))),
        _ck("request_answers", "url_format", format_check(TYPE_URL, text.regexp_match(URL))),
        _ck(
            "request_answers",
            "email_format",
            format_check(
                TYPE_EMAIL, sa.and_(text.regexp_match(EMAIL), text == sa.func.lower(text))
            ),
        ),
        _ck(
            "request_answers",
            "integer_is_whole",
            format_check(TYPE_INTEGER, sa.func.trunc(number) == number),
        ),
        _ck(
            "request_answers", "cedula_format", format_check(TYPE_CEDULA, text.regexp_match(CEDULA))
        ),
    )
    op.create_index("ix_request_answers_request_id", "request_answers", ["request_id"])
    op.create_index(
        "uq_request_answers_option",
        "request_answers",
        ["request_id", "field_id", "option_id"],
        unique=True,
        postgresql_where=option.is_not(None),
    )
    op.create_index(
        "uq_request_answers_single",
        "request_answers",
        ["request_id", "field_id"],
        unique=True,
        postgresql_where=option.is_(None),
    )
    op.create_index(
        "uq_request_answers_single_select",
        "request_answers",
        ["request_id", "field_id"],
        unique=True,
        postgresql_where=field_type == TYPE_SINGLE_SELECT,
    )

    op.create_table(
        "request_attachments",
        _uuid("id"),
        _uuid("request_id"),
        _int("form_version_id"),
        _int("field_id"),
        _smallint("field_type_id"),
        _uuid("uploaded_by"),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("storage_key", sa.String(500), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        _ts("created_at", now=True),
        _pk("request_attachments"),
        _ck("request_attachments", "file_size_positive", sa.column("file_size") > 0),
        _not_blank("request_attachments", "file_name"),
        _fk_composite(
            "request_attachments",
            "request_id",
            ["request_id", "form_version_id"],
            "research_product_requests",
            ["id", "form_version_id"],
        ),
        _fk_composite(
            "request_attachments",
            "field_id",
            ["field_id", "form_version_id", "field_type_id"],
            "form_fields",
            ["id", "form_version_id", "field_type_id"],
        ),
        _ck("request_attachments", "field_is_support", sa.column("field_type_id") == TYPE_SUPPORT),
        _fk("request_attachments", "uploaded_by", "users"),
        _ck(
            "request_attachments",
            "sha256_format",
            sa.column("sha256").regexp_match("^[0-9a-f]{64}$"),
        ),
        sa.UniqueConstraint("storage_key", name=op.f("uq_request_attachments_storage_key")),
        sa.UniqueConstraint("request_id", "sha256", name="uq_request_attachments_request_sha256"),
    )
    op.create_index("ix_request_attachments_request_id", "request_attachments", ["request_id"])
    op.create_index("ix_request_attachments_field_id", "request_attachments", ["field_id"])

    op.create_table(
        "user_product_assignments",
        _uuid("user_id"),
        _int("product_type_id"),
        sa.PrimaryKeyConstraint(
            "user_id", "product_type_id", name=op.f("pk_user_product_assignments")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_product_assignments_user_id_users"),
            ondelete="CASCADE",
        ),
        _fk("user_product_assignments", "product_type_id", "product_types"),
    )
    op.create_index(
        "ix_user_product_assignments_product", "user_product_assignments", ["product_type_id"]
    )

    op.create_table(
        "storage_counters",
        sa.Column("cedula", sa.String(15), nullable=False),
        _int("product_type_id"),
        sa.Column("last_value", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("cedula", "product_type_id", name=op.f("pk_storage_counters")),
        _ck("storage_counters", "cedula_format", sa.column("cedula").regexp_match(CEDULA)),
        _ck("storage_counters", "last_value_non_negative", sa.column("last_value") >= 0),
        _fk("storage_counters", "product_type_id", "product_types"),
    )

    op.create_table(
        "storage_folders",
        _uuid("request_id"),
        sa.Column("cedula", sa.String(15), nullable=False),
        _int("product_type_id"),
        sa.Column("sequence", sa.Integer(), nullable=False),
        _ts("created_at", now=True),
        _pk("storage_folders", "request_id"),
        _ck("storage_folders", "cedula_format", sa.column("cedula").regexp_match(CEDULA)),
        _ck("storage_folders", "sequence_positive", sa.column("sequence") >= 1),
        sa.UniqueConstraint(
            "cedula",
            "product_type_id",
            "sequence",
            name="uq_storage_folders_cedula_type_sequence",
        ),
        _fk("storage_folders", "request_id", "research_product_requests"),
        _fk("storage_folders", "product_type_id", "product_types"),
    )

    correction_status: ColumnClause[int] = sa.column("status_id")
    op.create_table(
        "request_corrections",
        _uuid("id"),
        _uuid("request_id"),
        _uuid("requested_by"),
        sa.Column("description", sa.Text(), nullable=False),
        _smallint("status_id"),
        _ts("created_at", now=True),
        _ts("resolved_at", nullable=True),
        _pk("request_corrections"),
        _not_blank("request_corrections", "description"),
        _ck(
            "request_corrections",
            "resolved_at_matches_status",
            sa.or_(
                sa.and_(
                    correction_status == CORRECTION_ABIERTA, sa.column("resolved_at").is_(None)
                ),
                sa.and_(
                    correction_status == CORRECTION_RESUELTA, sa.column("resolved_at").is_not(None)
                ),
            ),
        ),
        _fk("request_corrections", "request_id", "research_product_requests"),
        _fk("request_corrections", "requested_by", "users"),
        _fk("request_corrections", "status_id", "correction_statuses"),
    )
    op.create_index("ix_request_corrections_request_id", "request_corrections", ["request_id"])
    op.create_index(
        "uq_request_corrections_one_open",
        "request_corrections",
        ["request_id"],
        unique=True,
        postgresql_where=correction_status == CORRECTION_ABIERTA,
    )

    previous: ColumnClause[int] = sa.column("previous_status_id")
    new: ColumnClause[int] = sa.column("new_status_id")
    op.create_table(
        "request_status_history",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True)),
        _uuid("request_id"),
        _smallint("previous_status_id", nullable=True),
        _smallint("new_status_id"),
        _uuid("changed_by"),
        sa.Column("reason", sa.Text(), nullable=True),
        _ts("created_at", now=True),
        _pk("request_status_history"),
        _ck(
            "request_status_history", "status_changes", sa.or_(previous.is_(None), previous != new)
        ),
        _ck(
            "request_status_history",
            "creation_is_draft",
            sa.or_(previous.is_not(None), new == BORRADOR),
        ),
        _ck(
            "request_status_history",
            "reason_not_blank",
            sa.or_(
                sa.column("reason").is_(None),
                sa.func.length(sa.func.trim(sa.column("reason"))) > 0,
            ),
        ),
        _fk("request_status_history", "request_id", "research_product_requests"),
        _fk("request_status_history", "previous_status_id", "request_statuses"),
        _fk("request_status_history", "new_status_id", "request_statuses"),
        _fk("request_status_history", "changed_by", "users"),
    )
    op.create_index(
        "ix_request_status_history_request_created",
        "request_status_history",
        ["request_id", "created_at"],
    )

    op.create_table(
        "notifications",
        _uuid("id"),
        _uuid("user_id"),
        _uuid("request_id"),
        _smallint("status_id"),
        sa.Column("reason", sa.Text(), nullable=True),
        _ts("created_at", now=True),
        _ts("read_at", nullable=True),
        _pk("notifications"),
        _ck(
            "notifications",
            "reason_not_blank",
            sa.or_(
                sa.column("reason").is_(None),
                sa.func.length(sa.func.trim(sa.column("reason"))) > 0,
            ),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_notifications_user_id_users"),
            ondelete="CASCADE",
        ),
        _fk("notifications", "request_id", "research_product_requests"),
        _fk("notifications", "status_id", "request_statuses"),
    )
    op.create_index("ix_notifications_user_created", "notifications", ["user_id", "created_at"])
    op.create_index(
        "ix_notifications_unread",
        "notifications",
        ["user_id"],
        postgresql_where=sa.column("read_at").is_(None),
    )


def downgrade() -> None:
    # Orden inverso de dependencias; los índices se eliminan junto con su tabla.
    for table in (
        "notifications",
        "user_product_assignments",
        "storage_folders",
        "storage_counters",
        "request_status_history",
        "request_corrections",
        "request_attachments",
        "request_answers",
        "research_product_requests",
        "refresh_tokens",
        "auth_sessions",
        "audit_logs",
        "form_field_options",
        "form_field_document_types",
        "form_fields",
        "form_sections",
        "form_versions",
        "product_types",
        "users",
        "request_counters",
        "audit_actions",
        "field_types",
        "audit_categories",
        "value_kinds",
        "document_types",
        "form_statuses",
        "correction_statuses",
        "request_statuses",
        "roles",
    ):
        op.drop_table(table)
