import type { AssessmentReviewProvider } from '../api/assessmentReviewClient'
import type { AssessmentReviewRequestResponse } from '../types/assessmentReview'
import { findMockAdminReview, registerMockAdminReview } from './adminReviewProvider'

const results = new Map<string, AssessmentReviewRequestResponse>()

const currentResponse = (response: AssessmentReviewRequestResponse): AssessmentReviewRequestResponse => {
  if (!response.underwriterReviewId) return response
  const workflow = findMockAdminReview(response.underwriterReviewId)
  if (!workflow || workflow.triggerType !== 'CUSTOMER_ASSESSMENT_REVIEW') return response
  const resultCode = workflow.resultCode === 'ASSESSMENT_CONFIRMED'
    || workflow.resultCode === 'CORRECTION_REQUIRED'
    || workflow.resultCode === 'ADDITIONAL_INFORMATION_REQUIRED'
    || workflow.resultCode === 'ESCALATED'
    ? workflow.resultCode
    : null
  return {
    ...response,
    processing: {
      status: workflow.status,
      resultCode,
      startedAt: workflow.startedAt ?? null,
      completedAt: workflow.completedAt ?? null,
    },
  }
}

export const mockAssessmentReviewProvider: AssessmentReviewProvider = {
  async get(sessionId, signal) {
    if (signal.aborted) throw new DOMException('Aborted', 'AbortError')
    const existing = results.get(sessionId)
    return existing ? currentResponse(existing) : { sessionId, reviewRequest: null, underwriterReviewId: null, processing: null }
  },
  async request(sessionId, signal) {
    if (signal.aborted) throw new DOMException('Aborted', 'AbortError')
    const existing = results.get(sessionId)
    if (existing) return currentResponse(existing)
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
    registerMockAdminReview({
      reviewId: response.underwriterReviewId!,
      sessionId,
      triggerType: 'CUSTOMER_ASSESSMENT_REVIEW',
      triggerId: response.reviewRequest!.reviewRequestId,
      targetType: response.reviewRequest!.targetType,
      targetAssessmentId: response.reviewRequest!.targetAssessmentId,
      reasonCodes: [response.reviewRequest!.reasonCode],
      requestedAt: response.reviewRequest!.requestedAt,
      dataVersion: response.reviewRequest!.dataVersion,
      policyVersion: response.reviewRequest!.requestPolicyVersion,
      status: 'PENDING',
      demoOnly: true,
    })
    results.set(sessionId, response)
    return response
  },
}
