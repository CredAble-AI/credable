from app.schemas.base import ApiModel


class ApiErrorDetail(ApiModel):
    code: str
    message: str
    request_id: str
    retryable: bool


class ApiErrorResponse(ApiModel):
    error: ApiErrorDetail
