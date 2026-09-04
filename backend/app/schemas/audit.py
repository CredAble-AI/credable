from datetime import datetime
from enum import StrEnum

from app.schemas.base import ApiModel


class AuditStage(StrEnum):
    CASE_CREATED = "CASE_CREATED"
    SESSION_CREATED = "SESSION_CREATED"


class AuditActor(StrEnum):
    SYSTEM = "SYSTEM"


class AuditEvent(ApiModel):
    event_id: str
    case_id: str
    request_id: str
    stage: AuditStage
    timestamp: datetime
    actor: AuditActor
    input_version: str
    input_snapshot_hash: str
    output_summary: dict[str, str | bool]
    recommendation_policy_version: str | None = None
    model_version: str | None = None
    data_version: str | None = None
    policy_version: str | None = None


class SessionAuditEvent(ApiModel):
    event_id: str
    session_id: str
    request_id: str
    stage: AuditStage
    timestamp: datetime
    actor: AuditActor
    input_version: str
    input_snapshot_hash: str
    output_summary: dict[str, str | bool]
    data_version: str
