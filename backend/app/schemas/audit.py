from datetime import datetime
from enum import StrEnum

from app.schemas.base import ApiModel


class AuditStage(StrEnum):
    SESSION_CREATED = "SESSION_CREATED"
    CONSENT_GRANTED = "CONSENT_GRANTED"
    CONSENT_WITHDRAWN = "CONSENT_WITHDRAWN"
    DATA_SOURCE_REFRESHED = "DATA_SOURCE_REFRESHED"
    ASSESSMENT_RUN = "ASSESSMENT_RUN"
    POLICY_BOUNDARY_CHECKED = "POLICY_BOUNDARY_CHECKED"
    EVIDENCE_SELECTED = "EVIDENCE_SELECTED"
    EVIDENCE_SUBMITTED = "EVIDENCE_SUBMITTED"
    EVIDENCE_QUALITY_CHECKED = "EVIDENCE_QUALITY_CHECKED"
    SUPPLEMENTAL_ASSESSMENT_RUN = "SUPPLEMENTAL_ASSESSMENT_RUN"
    PRODUCT_CATALOG_REFRESHED = "PRODUCT_CATALOG_REFRESHED"
    PRODUCT_CONDITIONS_QUERIED = "PRODUCT_CONDITIONS_QUERIED"


class AuditActor(StrEnum):
    SYSTEM = "SYSTEM"


class SessionAuditEvent(ApiModel):
    event_id: str
    session_id: str
    request_id: str
    stage: AuditStage
    timestamp: datetime
    actor: AuditActor
    input_version: str
    input_snapshot_hash: str
    output_summary: dict[str, str | bool | int | float]
    data_version: str | None = None
    model_version: str | None = None
    policy_version: str | None = None


class AdminAuditEventListResponse(ApiModel):
    session_id: str
    demo_only: bool
    events: list[SessionAuditEvent]
    next_cursor: str | None = None
