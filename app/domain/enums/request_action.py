from enum import StrEnum


class RequestAction(StrEnum):
    """Acciones que mueven una solicitud entre estados. Nunca se persiste un estado del cliente."""

    SUBMIT = "SUBMIT"
    START_REVIEW = "START_REVIEW"
    REQUEST_CORRECTION = "REQUEST_CORRECTION"
    RESUBMIT = "RESUBMIT"
    APPROVE = "APPROVE"
    REJECT = "REJECT"
