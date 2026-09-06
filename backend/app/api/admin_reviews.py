from typing import Annotated

from fastapi import APIRouter, Query, Request

from app.schemas.error import ApiErrorResponse
from app.schemas.review_workflow import UnderwriterReviewStatus
from app.schemas.underwriter_review import (
    UnderwriterReviewCompleteRequest,
    UnderwriterReviewDetailResponse,
    UnderwriterReviewQueueResponse,
)
from app.services.underwriter_review_service import UnderwriterReviewQueueService

router = APIRouter(prefix="/v1/admin", tags=["admin"])


def get_underwriter_review_queue_service(request: Request) -> UnderwriterReviewQueueService:
    return request.app.state.underwriter_review_queue_service


@router.get(
    "/underwriter-reviews",
    response_model=UnderwriterReviewQueueResponse,
    response_model_exclude_none=True,
    responses={
        503: {"model": ApiErrorResponse},
    },
)
async def list_underwriter_reviews(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    review_status: Annotated[UnderwriterReviewStatus | None, Query(alias="status")] = None,
) -> UnderwriterReviewQueueResponse:
    return get_underwriter_review_queue_service(request).list(
        limit=limit,
        offset=offset,
        status=review_status,
    )


@router.get(
    "/underwriter-reviews/{review_id}",
    response_model=UnderwriterReviewDetailResponse,
    response_model_exclude_none=True,
    responses={
        404: {"model": ApiErrorResponse},
    },
)
async def get_underwriter_review(
    review_id: str,
    request: Request,
) -> UnderwriterReviewDetailResponse:
    return get_underwriter_review_queue_service(request).get(review_id)


@router.post(
    "/underwriter-reviews/{review_id}/claim",
    response_model=UnderwriterReviewDetailResponse,
    response_model_exclude_none=True,
    responses={
        404: {"model": ApiErrorResponse},
        409: {"model": ApiErrorResponse},
    },
)
async def claim_underwriter_review(
    review_id: str,
    request: Request,
) -> UnderwriterReviewDetailResponse:
    return get_underwriter_review_queue_service(request).claim(
        review_id,
        request.state.request_id,
    )


@router.post(
    "/underwriter-reviews/{review_id}/complete",
    response_model=UnderwriterReviewDetailResponse,
    response_model_exclude_none=True,
    responses={
        404: {"model": ApiErrorResponse},
        409: {"model": ApiErrorResponse},
    },
)
async def complete_underwriter_review(
    review_id: str,
    payload: UnderwriterReviewCompleteRequest,
    request: Request,
) -> UnderwriterReviewDetailResponse:
    return get_underwriter_review_queue_service(request).complete(
        review_id,
        payload.result_code,
        request.state.request_id,
    )
