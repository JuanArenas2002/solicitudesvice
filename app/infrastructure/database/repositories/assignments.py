from collections.abc import Collection
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.infrastructure.database.models.user_product_assignment import UserProductAssignmentModel


class SqlAlchemyProductAssignmentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def product_ids(self, user_id: UUID) -> frozenset[int]:
        return frozenset(
            self._session.scalars(
                select(UserProductAssignmentModel.product_type_id).where(
                    UserProductAssignmentModel.user_id == user_id
                )
            )
        )

    def all(self) -> dict[UUID, frozenset[int]]:
        grouped: dict[UUID, set[int]] = {}
        for user_id, product_id in self._session.execute(
            select(UserProductAssignmentModel.user_id, UserProductAssignmentModel.product_type_id)
        ):
            grouped.setdefault(user_id, set()).add(product_id)
        return {user_id: frozenset(ids) for user_id, ids in grouped.items()}

    def replace(self, user_id: UUID, product_ids: Collection[int]) -> None:
        self._session.execute(
            delete(UserProductAssignmentModel).where(UserProductAssignmentModel.user_id == user_id)
        )
        self._session.add_all(
            UserProductAssignmentModel(user_id=user_id, product_type_id=p) for p in product_ids
        )
        self._session.flush()
