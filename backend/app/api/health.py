from fastapi import APIRouter, Request

from app.core.config import settings
from app.schemas.health import HealthResponse, ReadinessCheck, ReadinessResponse
from app.services.case_service import CaseService
from app.services.session_service import CustomerSessionService

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def get_health() -> HealthResponse:
    """Report whether the API process is running."""
    return HealthResponse(service=settings.slug)


@router.get("/ready", response_model=ReadinessResponse)
async def get_readiness(request: Request) -> ReadinessResponse:
    """Report whether the currently configured application dependencies are ready."""
    case_service: CaseService = request.app.state.case_service
    session_service: CustomerSessionService = request.app.state.session_service
    statuses = {
        "application": True,
        **case_service.readiness(),
        **session_service.readiness(),
    }
    checks = [
        ReadinessCheck(name=name, status="ok" if ready else "error")
        for name, ready in statuses.items()
    ]
    overall_status = "ready" if all(statuses.values()) else "not_ready"
    return ReadinessResponse(status=overall_status, checks=checks)
