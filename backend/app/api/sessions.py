from fastapi import APIRouter, Request, status

from app.schemas.error import ApiErrorResponse
from app.schemas.session import (
    CustomerSessionState,
    DemoSessionCreateRequest,
    DemoSessionCreateResponse,
)
from app.services.session_service import CustomerSessionService

router = APIRouter(prefix="/v1/sessions", tags=["sessions"])


def get_session_service(request: Request) -> CustomerSessionService:
    return request.app.state.session_service


@router.post(
    "/demo",
    response_model=DemoSessionCreateResponse,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"model": ApiErrorResponse}},
)
async def create_demo_session(
    payload: DemoSessionCreateRequest,
    request: Request,
) -> DemoSessionCreateResponse:
    state = get_session_service(request).create_demo_session(
        payload.demo_profile_id,
        request.state.request_id,
    )
    return DemoSessionCreateResponse(
        session_id=state.session.session_id,
        session=state.session,
    )


@router.get(
    "/{session_id}",
    response_model=CustomerSessionState,
    responses={404: {"model": ApiErrorResponse}},
)
async def get_session(session_id: str, request: Request) -> CustomerSessionState:
    return get_session_service(request).get_session(session_id)
