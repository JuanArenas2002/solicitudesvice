from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.dto.page import Page, PageRequest
from app.application.queries.users import UserFilter
from app.domain.entities.user import User
from app.domain.exceptions.errors import DuplicateEmail
from app.domain.value_objects.email import Email
from app.infrastructure.database.catalog import ROLE_BY_ID, ROLE_IDS
from app.infrastructure.database.models.user import UserModel

EMAIL_UNIQUE_CONSTRAINT = "uq_users_email"


def to_entity(model: UserModel) -> User:
    return User(
        id=model.id,
        first_name=model.first_name,
        last_name=model.last_name,
        email=Email(model.email),
        password_hash=model.password_hash,
        role=ROLE_BY_ID[model.role_id],
        is_active=model.is_active,
        created_at=model.created_at,
        updated_at=model.updated_at,
        last_login_at=model.last_login_at,
    )


def _apply(model: UserModel, user: User) -> None:
    model.first_name = user.first_name
    model.last_name = user.last_name
    model.email = user.email.value
    model.password_hash = user.password_hash
    model.role_id = ROLE_IDS[user.role]
    model.is_active = user.is_active
    model.created_at = user.created_at
    model.updated_at = user.updated_at
    model.last_login_at = user.last_login_at


def _is_email_conflict(error: IntegrityError) -> bool:
    diag = getattr(error.orig, "diag", None)
    return getattr(diag, "constraint_name", None) == EMAIL_UNIQUE_CONSTRAINT


class SqlAlchemyUserRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, user_id: UUID) -> User | None:
        model = self._session.get(UserModel, user_id)
        return to_entity(model) if model else None

    def get_by_email(self, email: Email) -> User | None:
        model = self._session.scalars(
            select(UserModel).where(UserModel.email == email.value)
        ).one_or_none()
        return to_entity(model) if model else None

    def add(self, user: User) -> None:
        model = UserModel(id=user.id)
        _apply(model, user)
        self._session.add(model)
        self._flush()

    def save(self, user: User) -> None:
        model = self._session.get(UserModel, user.id)
        if model is None:
            raise LookupError(f"Usuario {user.id} no existe")
        _apply(model, user)
        self._flush()

    def list(self, filters: UserFilter, page: PageRequest) -> Page[User]:
        query = select(UserModel)
        if filters.role is not None:
            query = query.where(UserModel.role_id == ROLE_IDS[filters.role])
        if filters.is_active is not None:
            query = query.where(UserModel.is_active == filters.is_active)
        if filters.search and filters.search.strip():
            term = filters.search.strip()
            query = query.where(
                or_(
                    UserModel.first_name.icontains(term, autoescape=True),
                    UserModel.last_name.icontains(term, autoescape=True),
                    UserModel.email.icontains(term, autoescape=True),
                )
            )
        total = self._session.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = self._session.scalars(
            query.order_by(UserModel.last_name, UserModel.first_name, UserModel.id)
            .limit(page.limit)
            .offset(page.offset)
        ).all()
        return Page(
            items=tuple(to_entity(row) for row in rows),
            total=total,
            page=page.page,
            page_size=page.page_size,
        )

    def _flush(self) -> None:
        try:
            self._session.flush()
        except IntegrityError as error:
            if _is_email_conflict(error):
                raise DuplicateEmail("Ya existe un usuario con ese email") from error
            raise
