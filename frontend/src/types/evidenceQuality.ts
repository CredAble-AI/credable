export type EvidenceQualityDimension = 'PROVENANCE' | 'FRESHNESS' | 'AUTHENTICITY' | 'COMPLETENESS' | 'CONSISTENCY' | 'MANIPULATION_RISK'
export type EvidenceQualityDimensionStatus = 'PASSED' | 'FAILED' | 'NOT_VERIFIED'
export type EvidenceQualityStatus = 'ACCEPTED' | 'REJECTED' | 'REVIEW_REQUIRED'
export type EvidenceQualityNextAction = 'RUN_REASSESSMENT' | 'EXCLUDE_EVIDENCE' | 'UNDERWRITER_REVIEW'
export type EvidenceTrustChannel = 'SERVER_SIGNED_MANIFEST' | 'BANK_INTERNAL_LEDGER' | 'SOURCE_API' | 'PDF_DIGITAL_SIGNATURE' | 'ISSUER_REFERENCE' | 'UNVERIFIED_DOCUMENT'
export type EvidenceVerifiedScope = 'DOCUMENT_INTEGRITY' | 'MANIFEST_BINDING' | 'DEMO_ISSUER_IDENTITY'

export interface EvidenceTrustVerification {
  status: 'VERIFIED' | 'NOT_VERIFIED'
  channel: EvidenceTrustChannel
  verifiedScopes: EvidenceVerifiedScope[]
  algorithm: 'RS256' | null
  keyId: string | null
  rationaleCode: string
}

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
  trustVerification?: EvidenceTrustVerification | null
  demoOnly: true
}

export interface EvidenceQualityResponse {
  sessionId: string
  quality: EvidenceQualityState | null
}
