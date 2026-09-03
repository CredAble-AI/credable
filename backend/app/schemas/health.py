from typing import Literal

from app.schemas.base import ApiModel


class HealthResponse(ApiModel):
    status: Literal["ok"] = "ok"
    service: str


class ReadinessCheck(ApiModel):
    name: str
    status: Literal["ok", "error"] = "ok"


class ReadinessResponse(ApiModel):
    status: Literal["ready", "not_ready"] = "ready"
    checks: list[ReadinessCheck]
