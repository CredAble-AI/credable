from fastapi import APIRouter

from app.core.config import settings
from app.schemas.health import HealthResponse, ReadinessCheck, ReadinessResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def get_health() -> HealthResponse:
    """Report whether the API process is running."""
    return HealthResponse(service=settings.slug)


@router.get("/ready", response_model=ReadinessResponse)
async def get_readiness() -> ReadinessResponse:
    """Report whether the currently configured application dependencies are ready."""
    return ReadinessResponse(checks=[ReadinessCheck(name="application")])
