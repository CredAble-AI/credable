from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI
from fastapi import Request as FastAPIRequest
from fastapi.responses import JSONResponse

from app.api.cases import router as cases_router
from app.api.health import router as health_router
from app.core.config import settings
from app.core.errors import ResourceNotFoundError
from app.repositories.case_repository import SqliteCaseRepository
from app.schemas.error import ApiErrorDetail, ApiErrorResponse
from app.services.case_service import CaseService, DemoCaseCatalog


def build_case_service() -> CaseService:
    return CaseService(
        repository=SqliteCaseRepository(settings.database_path),
        catalog=DemoCaseCatalog(settings.demo_cases_path),
    )


def create_app(case_service: CaseService | None = None) -> FastAPI:
    resolved_case_service = case_service or build_case_service()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        resolved_case_service.initialize()
        yield

    application = FastAPI(
        title=settings.name,
        version=settings.version,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    application.state.case_service = resolved_case_service

    @application.middleware("http")
    async def attach_request_id(request: FastAPIRequest, call_next):
        request.state.request_id = f"req_{uuid4().hex}"
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @application.exception_handler(ResourceNotFoundError)
    async def handle_not_found(
        request: FastAPIRequest,
        error: ResourceNotFoundError,
    ) -> JSONResponse:
        response = ApiErrorResponse(
            error=ApiErrorDetail(
                code=error.code,
                message=error.message,
                request_id=request.state.request_id,
                retryable=error.retryable,
            )
        )
        return JSONResponse(
            status_code=error.status_code,
            content=response.model_dump(mode="json", by_alias=True),
        )

    application.include_router(health_router)
    application.include_router(cases_router)
    return application


app = create_app()
