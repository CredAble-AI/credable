import type { AssessmentReviewProvider } from '../api/assessmentReviewClient'
import type { AssessmentReviewRequestResponse } from '../types/assessmentReview'

const results = new Map<string, AssessmentReviewRequestResponse>()

export const mockAssessmentReviewProvider: AssessmentReviewProvider = {
  async get(sessionId, signal) {
    if (signal.aborted) throw new DOMException('Aborted', 'AbortError')
    return results.get(sessionId) ?? { sessionId, reviewRequest: null, underwriterReviewId: null, processing: null }
  },
  async request(sessionId, signal) {
    if (signal.aborted) throw new DOMException('Aborted', 'AbortError')
    const existing = results.get(sessionId)
    if (existing) return existing
    const response: AssessmentReviewRequestResponse = {
      sessionId,
      reviewRequest: {
        reviewRequestId: `arr_demo_${sessionId}`,
        targetType: 'BASELINE_ASSESSMENT',
        targetAssessmentId: `asm_demo_${sessionId}`,
        reasonCode: 'CUSTOMER_REQUESTED_ASSESSMENT_REVIEW',
        requestedAt: new Date().toISOString(),
        requestSnapshotHash: '0'.repeat(64),
        dataVersion: 'demo-v1',
        modelVersion: 'demo-assessment-v1',
        requestPolicyVersion: 'assessment-review-request-policy-v1',
        demoOnly: true,
      },
      underwriterReviewId: `uwr_demo_${sessionId}`,
      processing: { status: 'PENDING', resultCode: null, startedAt: null, completedAt: null },
    }
    results.set(sessionId, response)
    return response
  },
}
