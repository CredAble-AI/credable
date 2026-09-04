from fastapi import APIRouter, Request

from app.schemas.session import DemoProfileCatalogResponse
from app.services.session_service import CustomerSessionService

router = APIRouter(prefix="/v1/demo-profiles", tags=["demo-profiles"])


@router.get("", response_model=DemoProfileCatalogResponse)
async def list_demo_profiles(request: Request) -> DemoProfileCatalogResponse:
    session_service: CustomerSessionService = request.app.state.session_service
    return session_service.list_demo_profiles()
