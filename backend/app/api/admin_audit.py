from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Security
from fastapi.security import APIKeyHeader

from app.schemas.audit import AdminAuditEventListResponse
from app.schemas.error import ApiErrorResponse
from app.schemas.evidence_burden import AdminEvidenceBurdenResponse
from app.services.admin_audit_service import AdminAuditService
from app.services.evidence_burden_service import AdminEvidenceBurdenService

router = APIRouter(prefix="/v1/admin/sessions", tags=["admin"])
admin_api_key_header = APIKeyHeader(
    name="X-Admin-API-Key",
    scheme_name="AdminApiKey",
    auto_error=False,
)


def require_admin_api_key(
    request: Request,
    api_key: Annotated[str | None, Security(admin_api_key_header)],
) -> None:
    request.app.state.admin_authenticator.authenticate(api_key)


def get_admin_audit_service(request: Request) -> AdminAuditService:
    return request.app.state.admin_audit_service


def get_admin_evidence_burden_service(request: Request) -> AdminEvidenceBurdenService:
    return request.app.state.admin_evidence_burden_service


@router.get(
    "/{session_id}/audit-events",
    response_model=AdminAuditEventListResponse,
    responses={
        400: {"model": ApiErrorResponse},
        401: {"model": ApiErrorResponse},
        404: {"model": ApiErrorResponse},
        503: {"model": ApiErrorResponse},
    },
    dependencies=[Depends(require_admin_api_key)],
)
async def list_admin_audit_events(
    session_id: str,
    request: Request,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query()] = None,
) -> AdminAuditEventListResponse:
    return get_admin_audit_service(request).list_events(
        session_id,
        limit=limit,
        cursor=cursor,
    )


@router.get(
    "/{session_id}/evidence-burden",
    response_model=AdminEvidenceBurdenResponse,
    responses={
        401: {"model": ApiErrorResponse},
        404: {"model": ApiErrorResponse},
        409: {"model": ApiErrorResponse},
        503: {"model": ApiErrorResponse},
    },
    dependencies=[Depends(require_admin_api_key)],
)
async def get_admin_evidence_burden(
    session_id: str,
    request: Request,
) -> AdminEvidenceBurdenResponse:
    return get_admin_evidence_burden_service(request).get(session_id)
