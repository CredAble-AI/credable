from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.api.admin_audit import require_admin_api_key
from app.schemas.error import ApiErrorResponse
from app.schemas.underwriter_review import UnderwriterReviewQueueResponse
from app.services.underwriter_review_service import UnderwriterReviewQueueService

router = APIRouter(prefix="/v1/admin", tags=["admin"])


def get_underwriter_review_queue_service(request: Request) -> UnderwriterReviewQueueService:
    return request.app.state.underwriter_review_queue_service


@router.get(
    "/underwriter-reviews",
    response_model=UnderwriterReviewQueueResponse,
    responses={
        401: {"model": ApiErrorResponse},
        503: {"model": ApiErrorResponse},
    },
    dependencies=[Depends(require_admin_api_key)],
)
async def list_underwriter_reviews(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> UnderwriterReviewQueueResponse:
    return get_underwriter_review_queue_service(request).list(
        limit=limit,
        offset=offset,
    )
