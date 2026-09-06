import type { AdminReviewProvider } from '../api/adminReviewClient'
import type { ApiError } from '../types/api'
import type { AdminReviewQueueItem, AdminReviewResultCode, AdminReviewTriggerType } from '../types/adminReview'

const items: AdminReviewQueueItem[] = [
  { reviewId: 'uwr_demo_assessment', sessionId: 'ses_demo_sole', triggerType: 'CUSTOMER_ASSESSMENT_REVIEW', triggerId: 'arr_demo_assessment', targetType: 'SUPPLEMENTAL_ASSESSMENT', targetAssessmentId: 'sam_demo', reasonCodes: ['CUSTOMER_REQUESTED_ASSESSMENT_REVIEW'], requestedAt: '2026-09-06T02:00:00Z', dataVersion: 'demo-v1', policyVersion: 'assessment-review-request-policy-v1', status: 'PENDING', demoOnly: true },
  { reviewId: 'uwr_demo_evidence', sessionId: 'ses_demo_corp', triggerType: 'EVIDENCE_QUALITY', triggerId: 'evq_demo_evidence', evidenceType: 'RECENT_REVENUE_SUMMARY', reasonCodes: ['DEMO_FILE_HASH_MISMATCH'], requestedAt: '2026-09-06T01:10:00Z', dataVersion: 'demo-v1', policyVersion: 'demo-quality-v1', status: 'IN_REVIEW', startedAt: '2026-09-06T01:20:00Z', demoOnly: true },
]

const allowedResults: Record<AdminReviewTriggerType, AdminReviewResultCode[]> = {
  EVIDENCE_QUALITY: ['EVIDENCE_CONFIRMED', 'EVIDENCE_EXCLUDED', 'ADDITIONAL_INFORMATION_REQUIRED', 'ESCALATED'],
  CUSTOMER_ASSESSMENT_REVIEW: ['ASSESSMENT_CONFIRMED', 'CORRECTION_REQUIRED', 'ADDITIONAL_INFORMATION_REQUIRED', 'ESCALATED'],
}

const findReviewIndex = (reviewId: string) => {
  const index = items.findIndex((item) => item.reviewId === reviewId)
  if (index < 0) throw { code: 'UNDERWRITER_REVIEW_NOT_FOUND', message: '심사역 검토 요청을 찾을 수 없습니다.', retryable: false } satisfies ApiError
  return index
}

const assertNotAborted = (signal: AbortSignal) => {
  if (signal.aborted) throw new DOMException('Aborted', 'AbortError')
}

export const mockAdminReviewProvider: AdminReviewProvider = {
  async list(_apiKey, query, signal) {
    assertNotAborted(signal)
    const filtered = query.status ? items.filter((item) => item.status === query.status) : items
    return { totalCount: filtered.length, limit: query.limit, offset: query.offset, items: filtered.slice(query.offset, query.offset + query.limit), demoOnly: true }
  },
  async get(_apiKey, reviewId, signal) {
    assertNotAborted(signal)
    return { review: items[findReviewIndex(reviewId)] }
  },
  async claim(_apiKey, reviewId, signal) {
    assertNotAborted(signal)
    const index = findReviewIndex(reviewId)
    const review = items[index]
    if (review.status === 'COMPLETED') throw { code: 'UNDERWRITER_REVIEW_ALREADY_COMPLETED', message: '이미 완료된 검토 요청입니다.', retryable: false } satisfies ApiError
    if (review.status === 'PENDING') items[index] = { ...review, status: 'IN_REVIEW', startedAt: new Date().toISOString() }
    return { review: items[index] }
  },
  async complete(_apiKey, reviewId, resultCode, signal) {
    assertNotAborted(signal)
    const index = findReviewIndex(reviewId)
    const review = items[index]
    if (review.status === 'PENDING') throw { code: 'UNDERWRITER_REVIEW_NOT_CLAIMED', message: '먼저 검토 요청을 접수해주세요.', retryable: false } satisfies ApiError
    if (!allowedResults[review.triggerType].includes(resultCode)) throw { code: 'UNDERWRITER_REVIEW_RESULT_NOT_ALLOWED', message: '이 검토 유형에 사용할 수 없는 처리 결과입니다.', retryable: false } satisfies ApiError
    if (review.status === 'COMPLETED' && review.resultCode !== resultCode) throw { code: 'UNDERWRITER_REVIEW_RESULT_CONFLICT', message: '이미 다른 결과로 완료된 검토 요청입니다.', retryable: false } satisfies ApiError
    items[index] = { ...review, status: 'COMPLETED', resultCode, completedAt: review.completedAt ?? new Date().toISOString() }
    return { review: items[index] }
  },
}
