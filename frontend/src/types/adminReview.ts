import type { AssessmentReviewTargetType } from './assessmentReview'

export type AdminReviewStatus = 'PENDING' | 'IN_REVIEW' | 'COMPLETED'
export type AdminReviewTriggerType = 'EVIDENCE_QUALITY' | 'CUSTOMER_ASSESSMENT_REVIEW'
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
}

export interface AdminReviewCompleteRequest {
  resultCode: AdminReviewResultCode
}

export interface AdminReviewListQuery {
  limit: number
  offset: number
  status: AdminReviewStatus | null
}
