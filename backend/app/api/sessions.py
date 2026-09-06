from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile, status
from fastapi.responses import FileResponse

from app.schemas.assessment import (
    AssessmentComparisonResponse,
    AssessmentResponse,
    SupplementalAssessmentResponse,
    SupplementalAssessmentRunRequest,
)
from app.schemas.assessment_review import AssessmentReviewRequestResponse
from app.schemas.comparison import ProductComparisonResponse
from app.schemas.consent import ConsentListResponse, ConsentState
from app.schemas.data_source import DataSourceListResponse
from app.schemas.error import ApiErrorResponse
from app.schemas.evidence_consent import EvidenceConsentResponse
from app.schemas.evidence_file import EvidenceSubmissionOptionResponse
from app.schemas.evidence_quality import EvidenceQualityResponse
from app.schemas.evidence_selection import EvidenceSelectionResponse
from app.schemas.evidence_submission import (
    EvidenceSubmissionCreateRequest,
    EvidenceSubmissionResponse,
)
from app.schemas.policy_boundary import EvidenceResolutionResponse, PolicyBoundaryCheckResponse
from app.schemas.product import ProductCatalogResponse
from app.schemas.product_condition import ProductConditionQueryResponse
from app.schemas.session import (
    CustomerSessionState,
    DemoSessionCreateRequest,
    DemoSessionCreateResponse,
)
from app.services.assessment_review_service import AssessmentReviewRequestService
from app.services.assessment_service import (
    AssessmentComparisonService,
    AssessmentService,
    SupplementalAssessmentService,
)
from app.services.comparison_service import ProductComparisonService
from app.services.consent_service import ConsentService
from app.services.data_source_service import DataSourceService
from app.services.evidence_consent_service import EvidenceConsentService
from app.services.evidence_quality_service import EvidenceQualityService
from app.services.evidence_selection_service import EvidenceSelectionService
from app.services.evidence_submission_service import EvidenceSubmissionService
from app.services.policy_boundary_service import EvidenceResolutionService, PolicyBoundaryService
from app.services.product_catalog_service import ProductCatalogService
from app.services.product_condition_service import ProductConditionService
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


def get_assessment_review_request_service(request: Request) -> AssessmentReviewRequestService:
    return request.app.state.assessment_review_request_service


def get_supplemental_assessment_service(request: Request) -> SupplementalAssessmentService:
    return request.app.state.supplemental_assessment_service


def get_assessment_comparison_service(request: Request) -> AssessmentComparisonService:
    return request.app.state.assessment_comparison_service


def get_evidence_resolution_service(request: Request) -> EvidenceResolutionService:
    return request.app.state.evidence_resolution_service


def get_policy_boundary_service(request: Request) -> PolicyBoundaryService:
    return request.app.state.policy_boundary_service


def get_evidence_selection_service(request: Request) -> EvidenceSelectionService:
    return request.app.state.evidence_selection_service


def get_evidence_consent_service(request: Request) -> EvidenceConsentService:
    return request.app.state.evidence_consent_service


def get_evidence_submission_service(request: Request) -> EvidenceSubmissionService:
    return request.app.state.evidence_submission_service


def get_evidence_quality_service(request: Request) -> EvidenceQualityService:
    return request.app.state.evidence_quality_service


def get_product_catalog_service(request: Request) -> ProductCatalogService:
    return request.app.state.product_catalog_service


def get_product_condition_service(request: Request) -> ProductConditionService:
    return request.app.state.product_condition_service


def get_product_comparison_service(request: Request) -> ProductComparisonService:
    return request.app.state.product_comparison_service


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
        payload.business_borrower_type,
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


@router.get(
    "/{session_id}/assessment/review-request",
    response_model=AssessmentReviewRequestResponse,
    responses={404: {"model": ApiErrorResponse}},
)
async def get_assessment_review_request(
    session_id: str,
    request: Request,
) -> AssessmentReviewRequestResponse:
    return get_assessment_review_request_service(request).get_latest(session_id)


@router.post(
    "/{session_id}/assessment/review-request",
    response_model=AssessmentReviewRequestResponse,
    responses={
        404: {"model": ApiErrorResponse},
        409: {"model": ApiErrorResponse},
    },
)
async def request_assessment_review(
    session_id: str,
    request: Request,
) -> AssessmentReviewRequestResponse:
    return get_assessment_review_request_service(request).request(
        session_id,
        request.state.request_id,
    )


@router.get(
    "/{session_id}/assessment/supplemental",
    response_model=SupplementalAssessmentResponse,
    responses={404: {"model": ApiErrorResponse}},
)
async def get_supplemental_assessment(
    session_id: str,
    request: Request,
) -> SupplementalAssessmentResponse:
    return get_supplemental_assessment_service(request).get_latest(session_id)


@router.post(
    "/{session_id}/assessment/supplemental/run",
    response_model=SupplementalAssessmentResponse,
    responses={
        404: {"model": ApiErrorResponse},
        409: {"model": ApiErrorResponse},
    },
)
async def run_supplemental_assessment(
    session_id: str,
    payload: SupplementalAssessmentRunRequest,
    request: Request,
) -> SupplementalAssessmentResponse:
    return get_supplemental_assessment_service(request).run(
        session_id,
        payload.submission_id,
        request.state.request_id,
    )


@router.get(
    "/{session_id}/assessment/comparison",
    response_model=AssessmentComparisonResponse,
    responses={404: {"model": ApiErrorResponse}},
)
async def get_assessment_comparison(
    session_id: str,
    request: Request,
) -> AssessmentComparisonResponse:
    return get_assessment_comparison_service(request).get_latest(session_id)


@router.post(
    "/{session_id}/assessment/comparison",
    response_model=AssessmentComparisonResponse,
    responses={
        404: {"model": ApiErrorResponse},
        409: {"model": ApiErrorResponse},
    },
)
async def compare_assessments(
    session_id: str,
    request: Request,
) -> AssessmentComparisonResponse:
    return get_assessment_comparison_service(request).compare(
        session_id,
        request.state.request_id,
    )


@router.get(
    "/{session_id}/assessment/resolution",
    response_model=EvidenceResolutionResponse,
    responses={404: {"model": ApiErrorResponse}},
)
async def get_evidence_resolution(
    session_id: str,
    request: Request,
) -> EvidenceResolutionResponse:
    return get_evidence_resolution_service(request).get_latest(session_id)


@router.post(
    "/{session_id}/assessment/resolution",
    response_model=EvidenceResolutionResponse,
    responses={
        404: {"model": ApiErrorResponse},
        409: {"model": ApiErrorResponse},
    },
)
async def resolve_evidence_collection(
    session_id: str,
    request: Request,
) -> EvidenceResolutionResponse:
    return get_evidence_resolution_service(request).resolve(
        session_id,
        request.state.request_id,
    )


@router.get(
    "/{session_id}/assessment/boundary-check",
    response_model=PolicyBoundaryCheckResponse,
    responses={404: {"model": ApiErrorResponse}},
)
async def get_policy_boundary_check(
    session_id: str,
    request: Request,
) -> PolicyBoundaryCheckResponse:
    return get_policy_boundary_service(request).get_latest(session_id)


@router.post(
    "/{session_id}/assessment/boundary-check",
    response_model=PolicyBoundaryCheckResponse,
    responses={
        404: {"model": ApiErrorResponse},
        409: {"model": ApiErrorResponse},
    },
)
async def run_policy_boundary_check(
    session_id: str,
    request: Request,
) -> PolicyBoundaryCheckResponse:
    return get_policy_boundary_service(request).check(
        session_id,
        request.state.request_id,
    )


@router.get(
    "/{session_id}/evidence/next",
    response_model=EvidenceSelectionResponse,
    responses={404: {"model": ApiErrorResponse}},
)
async def get_evidence_selection(
    session_id: str,
    request: Request,
) -> EvidenceSelectionResponse:
    return get_evidence_selection_service(request).get_latest(session_id)


@router.post(
    "/{session_id}/evidence/next",
    response_model=EvidenceSelectionResponse,
    responses={
        404: {"model": ApiErrorResponse},
        409: {"model": ApiErrorResponse},
    },
)
async def select_next_evidence(
    session_id: str,
    request: Request,
) -> EvidenceSelectionResponse:
    return get_evidence_selection_service(request).select_next(
        session_id,
        request.state.request_id,
    )


@router.get(
    "/{session_id}/evidence/selections/{selection_id}/consent",
    response_model=EvidenceConsentResponse,
    responses={
        404: {"model": ApiErrorResponse},
        409: {"model": ApiErrorResponse},
    },
)
async def get_evidence_consent(
    session_id: str,
    selection_id: str,
    request: Request,
) -> EvidenceConsentResponse:
    return get_evidence_consent_service(request).get(session_id, selection_id)


@router.post(
    "/{session_id}/evidence/selections/{selection_id}/consent/grant",
    response_model=EvidenceConsentResponse,
    responses={
        404: {"model": ApiErrorResponse},
        409: {"model": ApiErrorResponse},
    },
)
async def grant_evidence_consent(
    session_id: str,
    selection_id: str,
    request: Request,
) -> EvidenceConsentResponse:
    return get_evidence_consent_service(request).grant(
        session_id,
        selection_id,
        request.state.request_id,
    )


@router.post(
    "/{session_id}/evidence/selections/{selection_id}/consent/withdraw",
    response_model=EvidenceConsentResponse,
    responses={
        404: {"model": ApiErrorResponse},
        409: {"model": ApiErrorResponse},
    },
)
async def withdraw_evidence_consent(
    session_id: str,
    selection_id: str,
    request: Request,
) -> EvidenceConsentResponse:
    return get_evidence_consent_service(request).withdraw(
        session_id,
        selection_id,
        request.state.request_id,
    )


@router.get(
    "/{session_id}/evidence/selections/{selection_id}/submission-option",
    response_model=EvidenceSubmissionOptionResponse,
    responses={
        404: {"model": ApiErrorResponse},
        409: {"model": ApiErrorResponse},
    },
)
async def get_evidence_submission_option(
    session_id: str,
    selection_id: str,
    request: Request,
) -> EvidenceSubmissionOptionResponse:
    return get_evidence_submission_service(request).get_submission_option(
        session_id,
        selection_id,
    )


@router.get(
    "/{session_id}/evidence/selections/{selection_id}/demo-file/download",
    response_class=FileResponse,
    responses={
        404: {"model": ApiErrorResponse},
        409: {"model": ApiErrorResponse},
    },
)
async def download_demo_evidence_file(
    session_id: str,
    selection_id: str,
    request: Request,
) -> FileResponse:
    file_path, definition = get_evidence_submission_service(request).get_demo_file(
        session_id,
        selection_id,
    )
    return FileResponse(
        path=file_path,
        media_type=definition.content_type,
        filename=definition.file_name,
    )


@router.get(
    "/{session_id}/evidence/submissions/latest",
    response_model=EvidenceSubmissionResponse,
    responses={404: {"model": ApiErrorResponse}},
)
async def get_latest_evidence_submission(
    session_id: str,
    request: Request,
) -> EvidenceSubmissionResponse:
    return get_evidence_submission_service(request).get_latest(session_id)


@router.post(
    "/{session_id}/evidence/submissions",
    response_model=EvidenceSubmissionResponse,
    responses={
        404: {"model": ApiErrorResponse},
        409: {"model": ApiErrorResponse},
    },
)
async def create_evidence_submission(
    session_id: str,
    payload: EvidenceSubmissionCreateRequest,
    request: Request,
) -> EvidenceSubmissionResponse:
    return get_evidence_submission_service(request).submit_demo(
        session_id,
        payload,
        request.state.request_id,
    )


@router.post(
    "/{session_id}/evidence/submissions/upload",
    response_model=EvidenceSubmissionResponse,
    responses={
        404: {"model": ApiErrorResponse},
        409: {"model": ApiErrorResponse},
        413: {"model": ApiErrorResponse},
        415: {"model": ApiErrorResponse},
        422: {"model": ApiErrorResponse},
    },
)
async def upload_demo_evidence_file(
    session_id: str,
    request: Request,
    selection_id: Annotated[str, Form(alias="selectionId", min_length=1)],
    file: Annotated[UploadFile, File()],
) -> EvidenceSubmissionResponse:
    service = get_evidence_submission_service(request)
    max_size_bytes = service.upload_limit(session_id, selection_id)
    try:
        content = await file.read(max_size_bytes + 1)
    finally:
        await file.close()
    return service.submit_demo_file(
        session_id=session_id,
        selection_id=selection_id,
        file_name=file.filename,
        content_type=file.content_type,
        content=content,
        request_id=request.state.request_id,
    )


@router.get(
    "/{session_id}/evidence/submissions/{submission_id}/quality",
    response_model=EvidenceQualityResponse,
    responses={404: {"model": ApiErrorResponse}},
)
async def get_evidence_quality(
    session_id: str,
    submission_id: str,
    request: Request,
) -> EvidenceQualityResponse:
    return get_evidence_quality_service(request).get(session_id, submission_id)


@router.post(
    "/{session_id}/evidence/submissions/{submission_id}/quality",
    response_model=EvidenceQualityResponse,
    responses={404: {"model": ApiErrorResponse}},
)
async def check_evidence_quality(
    session_id: str,
    submission_id: str,
    request: Request,
) -> EvidenceQualityResponse:
    return get_evidence_quality_service(request).check(
        session_id,
        submission_id,
        request.state.request_id,
    )


@router.get(
    "/{session_id}/products",
    response_model=ProductCatalogResponse,
    responses={404: {"model": ApiErrorResponse}},
)
async def get_product_catalog(
    session_id: str,
    request: Request,
) -> ProductCatalogResponse:
    return get_product_catalog_service(request).get_latest(session_id)


@router.post(
    "/{session_id}/products/refresh",
    response_model=ProductCatalogResponse,
    responses={404: {"model": ApiErrorResponse}},
)
async def refresh_product_catalog(
    session_id: str,
    request: Request,
) -> ProductCatalogResponse:
    return get_product_catalog_service(request).refresh(
        session_id,
        request.state.request_id,
    )


@router.get(
    "/{session_id}/product-conditions",
    response_model=ProductConditionQueryResponse,
    responses={404: {"model": ApiErrorResponse}},
)
async def get_product_conditions(
    session_id: str,
    request: Request,
) -> ProductConditionQueryResponse:
    return get_product_condition_service(request).get_latest(session_id)


@router.post(
    "/{session_id}/product-conditions/query",
    response_model=ProductConditionQueryResponse,
    responses={404: {"model": ApiErrorResponse}},
)
async def query_product_conditions(
    session_id: str,
    request: Request,
) -> ProductConditionQueryResponse:
    return get_product_condition_service(request).query(
        session_id,
        request.state.request_id,
    )


@router.get(
    "/{session_id}/comparison",
    response_model=ProductComparisonResponse,
    responses={404: {"model": ApiErrorResponse}},
)
async def get_product_comparison(
    session_id: str,
    request: Request,
) -> ProductComparisonResponse:
    return get_product_comparison_service(request).get_comparison(session_id)
