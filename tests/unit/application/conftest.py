import pytest

from app.application.commands.auth import LoginCommand
from app.application.commands.context import RequestContext
from app.application.dto.auth import AuthConfig, LoginResult
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
from app.application.use_cases.forms.seed_default_forms import SeedDefaultForms
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
from app.domain.entities.audit_entry import AuditEntry
from app.domain.entities.user import User
from app.domain.enums.audit_action import AuditAction
from app.domain.enums.role import Role
from app.domain.value_objects.actor import Actor
from tests.unit.application.fakes import (
    FakeAccessTokens,
    FakeClock,
    FakeFileStorage,
    FakeHasher,
    FakeJournalCatalog,
    FakeRefreshGenerator,
    FakeUnitOfWork,
    InMemoryDatabase,
)

CTX = RequestContext(correlation_id="corr-1", ip_address="203.0.113.7")
PASSWORD = "clave-correcta-123"


class World:
    """Ensambla los casos de uso con dobles en memoria."""

    def __init__(self) -> None:
        self.db = InMemoryDatabase()
        self.clock = FakeClock()
        self.hasher = FakeHasher()
        self.access = FakeAccessTokens()
        self.refresh = FakeRefreshGenerator()
        self.storage = FakeFileStorage()
        self.journals = FakeJournalCatalog()
        self.config = AuthConfig(
            refresh_token_ttl_seconds=7 * 86400, session_max_lifetime_seconds=30 * 86400
        )

    def uow(self) -> FakeUnitOfWork:
        return FakeUnitOfWork(self.db)

    # --- casos de uso ---
    def login(self) -> Login:
        return Login(self.uow, self.clock, self.hasher, self.access, self.refresh, self.config)

    def refresh_session(self) -> RefreshSession:
        return RefreshSession(self.uow, self.clock, self.access, self.refresh, self.config)

    def authenticate(self) -> AuthenticateAccessToken:
        return AuthenticateAccessToken(self.uow, self.clock, self.access)

    def logout(self) -> Logout:
        return Logout(self.uow, self.clock)

    def change_password(self) -> ChangeOwnPassword:
        return ChangeOwnPassword(self.uow, self.clock, self.hasher)

    def create_user(self) -> CreateUser:
        return CreateUser(self.uow, self.clock, self.hasher)

    def update_user(self) -> UpdateUser:
        return UpdateUser(self.uow, self.clock)

    def set_active(self) -> SetUserActive:
        return SetUserActive(self.uow, self.clock)

    def reset_password(self) -> ResetPassword:
        return ResetPassword(self.uow, self.clock, self.hasher)

    def get_user(self) -> GetUser:
        return GetUser(self.uow)

    def get_me(self) -> GetCurrentUser:
        return GetCurrentUser(self.uow)

    def list_users(self) -> ListUsers:
        return ListUsers(self.uow)

    def create_product_type(self) -> CreateProductType:
        return CreateProductType(self.uow, self.clock)

    def update_product_type(self) -> UpdateProductType:
        return UpdateProductType(self.uow, self.clock)

    def list_product_types(self) -> ListProductTypes:
        return ListProductTypes(self.uow)

    def create_draft(self) -> CreateFormDraft:
        return CreateFormDraft(self.uow, self.clock)

    def replace_draft(self) -> ReplaceFormDraft:
        return ReplaceFormDraft(self.uow, self.clock)

    def publish(self) -> PublishForm:
        return PublishForm(self.uow, self.clock)

    def get_form(self) -> GetFormVersion:
        return GetFormVersion(self.uow)

    def list_versions(self) -> ListFormVersions:
        return ListFormVersions(self.uow)

    def published_form(self) -> GetPublishedForm:
        return GetPublishedForm(self.uow)

    def seed_forms(self) -> SeedDefaultForms:
        return SeedDefaultForms(self.uow, self.clock)

    def create_request(self) -> CreateRequest:
        return CreateRequest(self.uow, self.clock)

    def update_answers(self) -> UpdateAnswers:
        return UpdateAnswers(self.uow, self.clock, self.journals)

    def submit(self) -> SubmitRequest:
        return SubmitRequest(self.uow, self.clock, self.journals)

    def start_review(self) -> StartReview:
        return StartReview(self.uow, self.clock)

    def request_correction(self) -> RequestCorrection:
        return RequestCorrection(self.uow, self.clock)

    def resubmit(self) -> ResubmitRequest:
        return ResubmitRequest(self.uow, self.clock, self.journals)

    def approve(self) -> ApproveRequest:
        return ApproveRequest(self.uow, self.clock)

    def reject(self) -> RejectRequest:
        return RejectRequest(self.uow, self.clock)

    def change_status(self) -> ChangeRequestStatus:
        return ChangeRequestStatus(self.uow, self.clock)

    def lookup_journal(self) -> LookupJournal:
        return LookupJournal(self.journals)

    def list_assignments(self) -> ListProductAssignments:
        return ListProductAssignments(self.uow)

    def list_notifications(self) -> ListNotifications:
        return ListNotifications(self.uow)

    def count_unread(self) -> CountUnreadNotifications:
        return CountUnreadNotifications(self.uow)

    def mark_read(self) -> MarkNotificationsRead:
        return MarkNotificationsRead(self.uow, self.clock)

    def get_user_products(self) -> GetUserProducts:
        return GetUserProducts(self.uow)

    def set_user_products(self) -> SetUserProducts:
        return SetUserProducts(self.uow, self.clock)

    def get_request(self) -> GetRequest:
        return GetRequest(self.uow)

    def list_requests(self) -> ListRequests:
        return ListRequests(self.uow)

    def history(self) -> GetRequestHistory:
        return GetRequestHistory(self.uow)

    def corrections(self) -> ListCorrections:
        return ListCorrections(self.uow)

    def article_product(self) -> int:
        """Carga el formulario de artículos (como el comando seed-forms) y devuelve su id."""
        admin = self.actor_for(self.add_user(Role.ADMIN, email="seed@example.org"))
        self.seed_forms().execute(admin, CTX)
        (product,) = self.db.state.product_types.values()
        assert product.id is not None
        return product.id

    def upload(self, max_bytes: int = 1024 * 1024) -> UploadAttachment:
        return UploadAttachment(self.uow, self.clock, self.storage, max_bytes)

    def list_attachments(self) -> ListAttachments:
        return ListAttachments(self.uow)

    def download(self) -> DownloadAttachment:
        return DownloadAttachment(self.uow, self.storage)

    def delete_attachment(self) -> DeleteAttachment:
        return DeleteAttachment(self.uow, self.clock, self.storage)

    # --- utilidades de prueba ---
    def add_user(
        self,
        role: Role = Role.MENTOR,
        *,
        email: str | None = None,
        password: str = PASSWORD,
        active: bool = True,
        first_name: str = "Ana",
        last_name: str = "Pérez",
    ) -> User:
        user = User.create(
            first_name=first_name,
            last_name=last_name,
            email=email or f"{role.value.lower()}{len(self.db.state.users)}@example.org",
            password_hash=self.hasher.hash(password),
            role=role,
            now=self.clock.now(),
        )
        user.is_active = active
        self.db.state.users[user.id] = user
        return user

    def login_as(self, user: User, password: str = PASSWORD) -> LoginResult:
        return self.login().execute(LoginCommand(user.email.value, password), CTX)

    def actor_for(self, user: User) -> Actor:
        return Actor(user.id, user.role)

    def audit_actions(self) -> list[AuditAction]:
        return [entry.action for entry in self.db.state.audit]

    def audit_of(self, action: AuditAction) -> list[AuditEntry]:
        return [entry for entry in self.db.state.audit if entry.action is action]


@pytest.fixture
def world() -> World:
    return World()
