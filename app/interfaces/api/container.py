"""Composition root: única pieza que conoce adaptadores y casos de uso a la vez.

Aquí se decide qué implementación concreta recibe cada puerto. Los routers no importan
infraestructura: piden al contenedor los casos de uso ya ensamblados.
"""

from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from app.application.dto.auth import AuthConfig
from app.application.ports.repositories.unit_of_work import UnitOfWorkFactory
from app.application.ports.services.journals import JournalCatalog
from app.application.use_cases.attachments.manage_attachments import (
    DeleteAttachment,
    DownloadAttachment,
    ListAttachments,
    UploadAttachment,
)
from app.application.use_cases.auth.authenticate import AuthenticateAccessToken
from app.application.use_cases.auth.change_password import ChangeOwnPassword
from app.application.use_cases.auth.login import Login
from app.application.use_cases.auth.logout import Logout
from app.application.use_cases.auth.refresh_session import RefreshSession
from app.application.use_cases.forms.manage_forms import (
    CreateFormDraft,
    GetFormVersion,
    GetPublishedForm,
    ListFormVersions,
    PublishForm,
    ReplaceFormDraft,
)
from app.application.use_cases.forms.manage_product_types import (
    CreateProductType,
    ListProductTypes,
    UpdateProductType,
)
from app.application.use_cases.journals import LookupJournal
from app.application.use_cases.notifications import (
    CountUnreadNotifications,
    ListNotifications,
    MarkNotificationsRead,
)
from app.application.use_cases.requests.commands import (
    ApproveRequest,
    ChangeRequestStatus,
    CreateRequest,
    RejectRequest,
    RequestCorrection,
    ResubmitRequest,
    StartReview,
    SubmitRequest,
    UpdateAnswers,
)
from app.application.use_cases.requests.queries import (
    GetRequest,
    GetRequestHistory,
    ListCorrections,
    ListRequests,
)
from app.application.use_cases.users.manage_assignments import (
    GetUserProducts,
    ListProductAssignments,
    SetUserProducts,
)
from app.application.use_cases.users.manage_users import (
    CreateUser,
    GetCurrentUser,
    GetUser,
    ListUsers,
    ResetPassword,
    SetUserActive,
    UpdateUser,
)
from app.config.settings import Settings
from app.infrastructure.clock import SystemClock
from app.infrastructure.database.session import create_db_engine, create_session_factory
from app.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork
from app.infrastructure.journals.http import HttpJournalCatalog
from app.infrastructure.security.access_tokens import JwtAccessTokenService
from app.infrastructure.security.passwords import Argon2PasswordHasher
from app.infrastructure.security.refresh_tokens import (
    HmacCsrfTokenService,
    SecureRefreshTokenGenerator,
)
from app.infrastructure.storage.local import LocalFileStorage


class Container:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._engine = create_db_engine(settings)
        session_factory = create_session_factory(self._engine)
        self.uow: UnitOfWorkFactory = lambda: SqlAlchemyUnitOfWork(session_factory)
        self.clock = SystemClock()
        self.storage = LocalFileStorage(Path(settings.storage_root))
        self.hasher = Argon2PasswordHasher()
        self.journals: JournalCatalog | None = (
            HttpJournalCatalog(settings.journals_url, settings.journals_timeout_seconds)
            if settings.journals_url
            else None
        )
        secret = settings.jwt_secret_key.get_secret_value()
        self.access_tokens = JwtAccessTokenService(
            secret,
            settings.jwt_algorithm,
            timedelta(minutes=settings.jwt_access_token_expire_minutes),
        )
        self.refresh_tokens = SecureRefreshTokenGenerator()
        self.csrf = HmacCsrfTokenService(secret)
        self.auth_config = AuthConfig(
            refresh_token_ttl_seconds=settings.jwt_refresh_token_expire_days * 86400,
            session_max_lifetime_seconds=settings.session_max_lifetime_days * 86400,
        )

    def close(self) -> None:
        self._engine.dispose()

    def ping(self) -> bool:
        """Consulta mínima para comprobar que la base de datos responde."""
        try:
            with self.uow() as uow:
                uow.users.get(uuid4())
            return True
        except Exception:  # noqa: BLE001 - cualquier fallo significa "no listo"
            return False

    # ---- auth ----
    def login(self) -> Login:
        return Login(
            self.uow,
            self.clock,
            self.hasher,
            self.access_tokens,
            self.refresh_tokens,
            self.auth_config,
        )

    def refresh_session(self) -> RefreshSession:
        return RefreshSession(
            self.uow, self.clock, self.access_tokens, self.refresh_tokens, self.auth_config
        )

    def authenticate(self) -> AuthenticateAccessToken:
        return AuthenticateAccessToken(self.uow, self.clock, self.access_tokens)

    def logout(self) -> Logout:
        return Logout(self.uow, self.clock)

    def change_password(self) -> ChangeOwnPassword:
        return ChangeOwnPassword(self.uow, self.clock, self.hasher)

    # ---- usuarios ----
    def create_user(self) -> CreateUser:
        return CreateUser(self.uow, self.clock, self.hasher)

    def update_user(self) -> UpdateUser:
        return UpdateUser(self.uow, self.clock)

    def set_user_active(self) -> SetUserActive:
        return SetUserActive(self.uow, self.clock)

    def reset_password(self) -> ResetPassword:
        return ResetPassword(self.uow, self.clock, self.hasher)

    def get_user(self) -> GetUser:
        return GetUser(self.uow)

    def list_product_assignments(self) -> ListProductAssignments:
        return ListProductAssignments(self.uow)

    def list_notifications(self) -> ListNotifications:
        return ListNotifications(self.uow)

    def count_unread_notifications(self) -> CountUnreadNotifications:
        return CountUnreadNotifications(self.uow)

    def mark_notifications_read(self) -> MarkNotificationsRead:
        return MarkNotificationsRead(self.uow, self.clock)

    def get_user_products(self) -> GetUserProducts:
        return GetUserProducts(self.uow)

    def set_user_products(self) -> SetUserProducts:
        return SetUserProducts(self.uow, self.clock)

    def get_me(self) -> GetCurrentUser:
        return GetCurrentUser(self.uow)

    def list_users(self) -> ListUsers:
        return ListUsers(self.uow)

    # ---- productos y formularios ----
    def create_product_type(self) -> CreateProductType:
        return CreateProductType(self.uow, self.clock)

    def update_product_type(self) -> UpdateProductType:
        return UpdateProductType(self.uow, self.clock)

    def list_product_types(self) -> ListProductTypes:
        return ListProductTypes(self.uow)

    def create_form_draft(self) -> CreateFormDraft:
        return CreateFormDraft(self.uow, self.clock)

    def replace_form_draft(self) -> ReplaceFormDraft:
        return ReplaceFormDraft(self.uow, self.clock)

    def publish_form(self) -> PublishForm:
        return PublishForm(self.uow, self.clock)

    def get_form_version(self) -> GetFormVersion:
        return GetFormVersion(self.uow)

    def list_form_versions(self) -> ListFormVersions:
        return ListFormVersions(self.uow)

    def get_published_form(self) -> GetPublishedForm:
        return GetPublishedForm(self.uow)

    # ---- soportes ----
    def upload_attachment(self) -> UploadAttachment:
        return UploadAttachment(
            self.uow, self.clock, self.storage, self.settings.attachment_max_bytes
        )

    def list_attachments(self) -> ListAttachments:
        return ListAttachments(self.uow)

    def download_attachment(self) -> DownloadAttachment:
        return DownloadAttachment(self.uow, self.storage)

    def delete_attachment(self) -> DeleteAttachment:
        return DeleteAttachment(self.uow, self.clock, self.storage)

    # ---- solicitudes ----
    def create_request(self) -> CreateRequest:
        return CreateRequest(self.uow, self.clock)

    def update_answers(self) -> UpdateAnswers:
        return UpdateAnswers(self.uow, self.clock, self.journals)

    def submit_request(self) -> SubmitRequest:
        return SubmitRequest(self.uow, self.clock, self.journals)

    def start_review(self) -> StartReview:
        return StartReview(self.uow, self.clock)

    def request_correction(self) -> RequestCorrection:
        return RequestCorrection(self.uow, self.clock)

    def resubmit_request(self) -> ResubmitRequest:
        return ResubmitRequest(self.uow, self.clock, self.journals)

    def approve_request(self) -> ApproveRequest:
        return ApproveRequest(self.uow, self.clock)

    def reject_request(self) -> RejectRequest:
        return RejectRequest(self.uow, self.clock)

    def change_request_status(self) -> ChangeRequestStatus:
        return ChangeRequestStatus(self.uow, self.clock)

    def lookup_journal(self) -> LookupJournal:
        return LookupJournal(self.journals)

    def get_request(self) -> GetRequest:
        return GetRequest(self.uow)

    def list_requests(self) -> ListRequests:
        return ListRequests(self.uow)

    def request_history(self) -> GetRequestHistory:
        return GetRequestHistory(self.uow)

    def list_corrections(self) -> ListCorrections:
        return ListCorrections(self.uow)
