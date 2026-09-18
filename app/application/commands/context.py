from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RequestContext:
    """Datos de la petición HTTP que la auditoría necesita (sin acoplar a FastAPI)."""

    correlation_id: str | None = None
    ip_address: str | None = None
