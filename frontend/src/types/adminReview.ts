import type { AssessmentReviewTargetType } from './assessmentReview'
import type { AssessmentComparisonState } from './assessmentComparison'
import type { AssessmentState } from './assessment'
import type { EvidenceQualityState } from './evidenceQuality'
import type { EvidenceResolutionState } from './evidenceResolution'
import type { EvidenceSelectionState } from './evidenceSelection'
import type { EvidenceSubmissionState } from './evidenceSubmission'
import type { PolicyBoundaryCheckState } from './policyBoundary'
import type { SupplementalAssessmentState } from './supplementalAssessment'

export type AdminReviewStatus = 'PENDING' | 'IN_REVIEW' | 'COMPLETED'
export type AdminReviewTriggerType =
  | 'EVIDENCE_QUALITY'
  | 'CUSTOMER_ASSESSMENT_REVIEW'
  | 'POLICY_BOUNDARY'
  | 'EVIDENCE_SELECTION'
  | 'EVIDENCE_RESOLUTION'
export type AdminReviewResultCode = 'EVIDENCE_CONFIRMED' | 'EVIDENCE_EXCLUDED' | 'ASSESSMENT_CONFIRMED' | 'CORRECTION_REQUIRED' | 'ADDITIONAL_INFORMATION_REQUIRED' | 'ESCALATED'

export interface AdminReviewQueueItem {
  reviewId: string
  sessionId: string
  triggerType: AdminReviewTriggerType
  triggerId: string
  evidenceType?: string
  targetType?: AssessmentReviewTargetType
  targetAssessmentId?: string
  reasonCodes: string[]
  requestedAt: string
  dataVersion: string
  policyVersion: string
  status: AdminReviewStatus
  resultCode?: AdminReviewResultCode
  decisionNote?: string
  startedAt?: string
  completedAt?: string
  demoOnly: boolean
}

export interface AdminReviewQueueResponse {
  totalCount: number
  limit: number
  offset: number
  items: AdminReviewQueueItem[]
  demoOnly: true
}

export interface AdminReviewDetailResponse {
  review: AdminReviewQueueItem
  context?: AdminReviewCaseContext
}

export interface AdminReviewCaseContext {
  assessment?: AssessmentState | null
  boundaryCheck?: PolicyBoundaryCheckState | null
  selection?: EvidenceSelectionState | null
  submission?: EvidenceSubmissionState | null
  quality?: EvidenceQualityState | null
  supplementalAssessment?: SupplementalAssessmentState | null
  comparison?: AssessmentComparisonState | null
  resolution?: EvidenceResolutionState | null
}

export interface AdminReviewCompleteRequest {
  resultCode: AdminReviewResultCode
  decisionNote: string
}

export interface AdminReviewListQuery {
  limit: number
  offset: number
  status: AdminReviewStatus | null
}
