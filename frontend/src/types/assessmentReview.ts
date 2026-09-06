export type AssessmentReviewTargetType = 'BASELINE_ASSESSMENT' | 'SUPPLEMENTAL_ASSESSMENT'
export type AssessmentReviewProcessingStatus = 'PENDING' | 'IN_REVIEW' | 'COMPLETED'
export type CustomerAssessmentReviewReason = 'INCORRECT_INFORMATION' | 'MISSING_RECENT_INFORMATION' | 'EXCLUDED_EVIDENCE_DISPUTED'
export type AssessmentReviewResultCode = 'ASSESSMENT_CONFIRMED' | 'CORRECTION_REQUIRED' | 'ADDITIONAL_INFORMATION_REQUIRED' | 'ESCALATED'

export interface AssessmentReviewRequestState {
  reviewRequestId: string
  targetType: AssessmentReviewTargetType
  targetAssessmentId: string
  reasonCode: 'CUSTOMER_REQUESTED_ASSESSMENT_REVIEW'
  customerReasonCode: CustomerAssessmentReviewReason | null
  requestedAt: string
  requestSnapshotHash: string
  dataVersion: string
  modelVersion: string
  requestPolicyVersion: 'assessment-review-request-policy-v1'
  demoOnly: true
}

export interface AssessmentReviewProcessing {
  status: AssessmentReviewProcessingStatus
  resultCode: AssessmentReviewResultCode | null
  startedAt: string | null
  completedAt: string | null
}

export interface AssessmentReviewRequestResponse {
  sessionId: string
  reviewRequest: AssessmentReviewRequestState | null
  underwriterReviewId: string | null
  processing: AssessmentReviewProcessing | null
}
