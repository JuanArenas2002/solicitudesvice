class DomainError(Exception):
    """Base de los errores de negocio. No conoce HTTP: la capa de interfaz los traduce."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidValue(DomainError):
    def __init__(self, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field


class PasswordPolicyViolation(InvalidValue):
    pass


class IncompleteProduct(DomainError):
    def __init__(self, missing: tuple[str, ...]) -> None:
        super().__init__("El producto está incompleto: " + ", ".join(missing))
        self.missing = missing


class Unauthorized(DomainError):
    pass


class RefreshTokenReuse(Unauthorized):
    pass


class Forbidden(DomainError):
    pass


class RequestNotFound(DomainError):
    """También cuando la solicitud existe pero el actor no puede verla (no revela existencia)."""


class InvalidStatusTransition(DomainError):
    pass


class InvalidRequestState(DomainError):
    pass


class ConcurrentModification(DomainError):
    pass


class UserNotFound(DomainError):
    pass


class DuplicateEmail(DomainError):
    pass


class ProductTypeNotFound(DomainError):
    pass


class DuplicateProductType(DomainError):
    pass


class FormVersionNotFound(DomainError):
    pass


class FormNotEditable(DomainError):
    """Solo los borradores se editan o publican; una versión publicada es inmutable."""


class FormDraftExists(DomainError):
    pass


class FileTooLarge(InvalidValue):
    pass


class AttachmentNotFound(DomainError):
    pass


class DuplicateAttachment(DomainError):
    pass


class AttachmentLimitReached(DomainError):
    pass


class CedulaLocked(DomainError):
    """La cédula ya define la carpeta de los soportes y no puede cambiar."""


class JournalNotFound(DomainError):
    """El ISSN no está registrado en el catálogo de revistas."""


class JournalServiceUnavailable(DomainError):
    """No se pudo consultar el catálogo de revistas (red, tiempo agotado, respuesta inválida)."""
