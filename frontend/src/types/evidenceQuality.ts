export type EvidenceQualityDimension = 'PROVENANCE' | 'FRESHNESS' | 'AUTHENTICITY' | 'COMPLETENESS' | 'CONSISTENCY' | 'MANIPULATION_RISK'
export type EvidenceQualityDimensionStatus = 'PASSED' | 'FAILED' | 'NOT_VERIFIED'
export type EvidenceQualityStatus = 'ACCEPTED' | 'REJECTED' | 'REVIEW_REQUIRED'
export type EvidenceQualityNextAction = 'RUN_REASSESSMENT' | 'EXCLUDE_EVIDENCE' | 'UNDERWRITER_REVIEW'

export interface EvidenceQualityDimensionResult {
  dimension: EvidenceQualityDimension
  status: EvidenceQualityDimensionStatus
  rationaleCode: string
}

export interface EvidenceQualityState {
  qualityCheckId: string
  submissionId: string
  evidenceType: string
  status: EvidenceQualityStatus
  checks: EvidenceQualityDimensionResult[]
  rejectionCodes: string[]
  suspicionCodes: string[]
  eligibleForReassessment: boolean
  nextAction: EvidenceQualityNextAction
  underwriterRequired: boolean
  checkedAt: string
  submissionSnapshotHash: string
  dataVersion: string
  qualityPolicyVersion: string
  demoOnly: true
}

export interface EvidenceQualityResponse {
  sessionId: string
  quality: EvidenceQualityState | null
}
