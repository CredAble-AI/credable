import type { ConsentSourceType } from './consent'
import type { EvidenceResolutionStatus } from './evidenceResolution'

export interface EvidenceTypeBurdenBreakdown {
  evidenceType: string
  sourceType: ConsentSourceType
  requestCount: number
  submissionCount: number
  acceptedCount: number
  rejectedCount: number
  reviewRequiredCount: number
  firstRequestedAt: string
  lastRequestedAt: string
}

export interface AdminEvidenceBurdenResponse {
  sessionId: string
  asOf: string
  evidenceRequestCount: number
  repeatedRequestCount: number
  availableRequestCount: number
  requestableRequestCount: number
  consentRequiredRequestCount: number
  unavailableRequestCount: number
  submissionCount: number
  pendingSubmissionCount: number
  acceptedCount: number
  rejectedCount: number
  reviewRequiredCount: number
  unverifiedSubmissionCount: number
  failedQualityDimensionCount: number
  supplementalAssessmentCount: number
  resolutionCount: number
  latestResolutionStatus: EvidenceResolutionStatus | null
  collectionStopped: boolean | null
  maxRequestIteration: number
  evidenceTypes: EvidenceTypeBurdenBreakdown[]
  measurementVersion: 'evidence-burden-metrics-v1'
  policyThresholdApplied: false
  demoOnly: boolean
}
