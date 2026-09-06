import type { AdminReviewProvider } from '../api/adminReviewClient'
import type { AdminReviewQueueItem } from '../types/adminReview'

const items: AdminReviewQueueItem[] = [
  { reviewId: 'uwr_demo_assessment', sessionId: 'ses_demo_sole', triggerType: 'CUSTOMER_ASSESSMENT_REVIEW', triggerId: 'arr_demo_assessment', targetType: 'SUPPLEMENTAL_ASSESSMENT', targetAssessmentId: 'sam_demo', reasonCodes: ['CUSTOMER_REQUESTED_ASSESSMENT_REVIEW'], requestedAt: '2026-09-06T02:00:00Z', dataVersion: 'demo-v1', policyVersion: 'assessment-review-request-policy-v1', status: 'PENDING', demoOnly: true },
  { reviewId: 'uwr_demo_evidence', sessionId: 'ses_demo_corp', triggerType: 'EVIDENCE_QUALITY', triggerId: 'evq_demo_evidence', evidenceType: 'RECENT_REVENUE_SUMMARY', reasonCodes: ['DEMO_FILE_HASH_MISMATCH'], requestedAt: '2026-09-06T01:10:00Z', dataVersion: 'demo-v1', policyVersion: 'demo-quality-v1', status: 'IN_REVIEW', startedAt: '2026-09-06T01:20:00Z', demoOnly: true },
]

export const mockAdminReviewProvider: AdminReviewProvider = {
  async list(_apiKey, query, signal) {
    if (signal.aborted) throw new DOMException('Aborted', 'AbortError')
    const filtered = query.status ? items.filter((item) => item.status === query.status) : items
    return { totalCount: filtered.length, limit: query.limit, offset: query.offset, items: filtered.slice(query.offset, query.offset + query.limit), demoOnly: true }
  },
}
