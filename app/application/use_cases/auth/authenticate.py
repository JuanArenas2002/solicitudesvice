from app.application.ports.repositories.unit_of_work import UnitOfWorkFactory
from app.application.ports.services.clock import Clock
from app.application.ports.services.security import AccessTokenService
from app.domain.enums.role import Role
from app.domain.exceptions.errors import Unauthorized
from app.domain.value_objects.actor import Actor


class AuthenticateAccessToken:
    """Se ejecuta en CADA request protegido: el rol y el estado se leen de la BD, no del token."""

    def __init__(
        self, uow_factory: UnitOfWorkFactory, clock: Clock, access_tokens: AccessTokenService
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._access_tokens = access_tokens

    def execute(self, token: str) -> Actor:
        claims = self._access_tokens.decode(token)  # firma y expiración
        now = self._clock.now()
        with self._uow_factory() as uow:
            session = uow.sessions.get_session(claims.session_id)
            user = uow.users.get(claims.user_id)
            scope = (
                uow.assignments.product_ids(claims.user_id)
                if user is not None and user.role is Role.ADMINISTRATIVO
                else None
            )
        if (
            session is None
            or user is None
            or session.user_id != user.id
            or not session.is_active(now)
            or not user.is_active
        ):
            raise Unauthorized("Sesión inválida")
        return Actor(user_id=user.id, role=user.role, session_id=session.id, product_scope=scope)
