export type EvidenceResolutionStatus = 'RESOLVED' | 'MORE_EVIDENCE_REQUIRED' | 'HUMAN_REVIEW'
export type EvidenceResolutionNextAction = 'SHOW_UPDATED_RESULTS' | 'REQUEST_NEXT_EVIDENCE' | 'UNDERWRITER_REVIEW'

export interface EvidenceResolutionState {
  resolutionId: string
  comparisonId: string
  supplementalAssessmentId: string
  status: EvidenceResolutionStatus
  nextAction: EvidenceResolutionNextAction
  stopEvidenceCollection: boolean
  underwriterRequired: boolean
  reasonCode: string
  possibleRoutes: string[]
  crossedBoundaryCodes: string[]
  resolvedAt: string
  calibrationVersion: string | null
  boundaryPolicyVersion: string
  demoOnly: true
}

export interface EvidenceResolutionResponse {
  sessionId: string
  resolution: EvidenceResolutionState | null
}

export interface EvidenceResolutionContext {
  comparisonId: string
  supplementalAssessmentId: string
}
