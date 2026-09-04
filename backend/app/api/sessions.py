from fastapi import APIRouter, Request, status

from app.schemas.assessment import AssessmentResponse
from app.schemas.consent import ConsentListResponse, ConsentState
from app.schemas.data_source import DataSourceListResponse
from app.schemas.error import ApiErrorResponse
from app.schemas.session import (
    CustomerSessionState,
    DemoSessionCreateRequest,
    DemoSessionCreateResponse,
)
from app.services.assessment_service import AssessmentService
from app.services.consent_service import ConsentService
from app.services.data_source_service import DataSourceService
from app.services.session_service import CustomerSessionService

router = APIRouter(prefix="/v1/sessions", tags=["sessions"])


def get_session_service(request: Request) -> CustomerSessionService:
    return request.app.state.session_service


def get_consent_service(request: Request) -> ConsentService:
    return request.app.state.consent_service


def get_data_source_service(request: Request) -> DataSourceService:
    return request.app.state.data_source_service


def get_assessment_service(request: Request) -> AssessmentService:
    return request.app.state.assessment_service


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


@router.get(
    "/{session_id}/consents",
    response_model=ConsentListResponse,
    responses={404: {"model": ApiErrorResponse}},
)
async def list_consents(session_id: str, request: Request) -> ConsentListResponse:
    return get_consent_service(request).list_consents(session_id)


@router.post(
    "/{session_id}/consents/{source_type}/grant",
    response_model=ConsentState,
    responses={404: {"model": ApiErrorResponse}},
)
async def grant_consent(
    session_id: str,
    source_type: str,
    request: Request,
) -> ConsentState:
    return get_consent_service(request).grant_consent(
        session_id,
        source_type,
        request.state.request_id,
    )


@router.post(
    "/{session_id}/consents/{source_type}/withdraw",
    response_model=ConsentState,
    responses={
        404: {"model": ApiErrorResponse},
        409: {"model": ApiErrorResponse},
    },
)
async def withdraw_consent(
    session_id: str,
    source_type: str,
    request: Request,
) -> ConsentState:
    return get_consent_service(request).withdraw_consent(
        session_id,
        source_type,
        request.state.request_id,
    )


@router.get(
    "/{session_id}/data-sources",
    response_model=DataSourceListResponse,
    responses={404: {"model": ApiErrorResponse}},
)
async def list_data_sources(
    session_id: str,
    request: Request,
) -> DataSourceListResponse:
    return get_data_source_service(request).list_states(session_id)


@router.post(
    "/{session_id}/data-sources/refresh",
    response_model=DataSourceListResponse,
    responses={404: {"model": ApiErrorResponse}},
)
async def refresh_data_sources(
    session_id: str,
    request: Request,
) -> DataSourceListResponse:
    return get_data_source_service(request).refresh(
        session_id,
        request.state.request_id,
    )


@router.get(
    "/{session_id}/assessment",
    response_model=AssessmentResponse,
    responses={404: {"model": ApiErrorResponse}},
)
async def get_assessment(
    session_id: str,
    request: Request,
) -> AssessmentResponse:
    return get_assessment_service(request).get_latest(session_id)


@router.post(
    "/{session_id}/assessment/run",
    response_model=AssessmentResponse,
    responses={404: {"model": ApiErrorResponse}},
)
async def run_assessment(
    session_id: str,
    request: Request,
) -> AssessmentResponse:
    return get_assessment_service(request).run(
        session_id,
        request.state.request_id,
    )
