from fastapi import APIRouter, Request

from app.schemas.case import CaseState, DemoCaseCreateRequest, DemoCaseCreateResponse
from app.schemas.error import ApiErrorResponse
from app.services.case_service import CaseService

router = APIRouter(prefix="/v1/cases", tags=["cases"])


def get_case_service(request: Request) -> CaseService:
    return request.app.state.case_service


@router.post(
    "/demo",
    response_model=DemoCaseCreateResponse,
    responses={404: {"model": ApiErrorResponse}},
)
async def create_demo_case(
    payload: DemoCaseCreateRequest,
    request: Request,
) -> DemoCaseCreateResponse:
    service = get_case_service(request)
    state = service.create_demo_case(payload.demo_case_id, request.state.request_id)
    return DemoCaseCreateResponse(case_id=state.case.case_id, case=state.case)


@router.get(
    "/{case_id}",
    response_model=CaseState,
    responses={404: {"model": ApiErrorResponse}},
)
async def get_case(case_id: str, request: Request) -> CaseState:
    return get_case_service(request).get_case(case_id)
