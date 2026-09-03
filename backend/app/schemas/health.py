from typing import Literal

from pydantic import BaseModel, ConfigDict


class ApiResponse(BaseModel):
    model_config = ConfigDict(frozen=True)


class HealthResponse(ApiResponse):
    status: Literal["ok"] = "ok"
    service: str


class ReadinessCheck(ApiResponse):
    name: str
    status: Literal["ok"] = "ok"


class ReadinessResponse(ApiResponse):
    status: Literal["ready"] = "ready"
    checks: list[ReadinessCheck]
