export type AuditActor = 'SYSTEM' | 'CUSTOMER' | 'UNDERWRITER'
export type AuditStage = 'SESSION_CREATED' | 'CONSENT_GRANTED' | 'CONSENT_WITHDRAWN' | 'DATA_SOURCE_REFRESHED' | 'ASSESSMENT_RUN' | 'POLICY_BOUNDARY_CHECKED' | 'EVIDENCE_SELECTED' | 'EVIDENCE_CONSENT_GRANTED' | 'EVIDENCE_CONSENT_WITHDRAWN' | 'EVIDENCE_SUBMITTED' | 'EVIDENCE_QUALITY_CHECKED' | 'SUPPLEMENTAL_ASSESSMENT_RUN' | 'ASSESSMENT_COMPARED' | 'EVIDENCE_COLLECTION_RESOLVED' | 'ASSESSMENT_REVIEW_REQUESTED' | 'UNDERWRITER_REVIEW_STARTED' | 'UNDERWRITER_REVIEW_COMPLETED' | 'PRODUCT_CATALOG_REFRESHED' | 'PRODUCT_CONDITIONS_QUERIED'

export interface SessionAuditEvent {
  eventId: string
  sessionId: string
  requestId: string
  stage: AuditStage
  timestamp: string
  actor: AuditActor
  inputVersion: string
  inputSnapshotHash: string
  outputSummary: Record<string, string | boolean | number>
  dataVersion: string | null
  modelVersion: string | null
  policyVersion: string | null
}

export interface AdminAuditEventListResponse {
  sessionId: string
  demoOnly: boolean
  events: SessionAuditEvent[]
  nextCursor: string | null
}
