from fastapi import APIRouter, Response, status

from app.interfaces.api.dependencies import ContainerDep

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", summary="El proceso está vivo")
def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready", summary="El servicio puede atender (la base de datos responde)")
def readiness(response: Response, container: ContainerDep) -> dict[str, str]:
    if container.ping():
        return {"status": "ok", "database": "up"}
    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "unavailable", "database": "down"}
