import type { AdminEvidenceBurdenProvider } from '../api/adminEvidenceBurdenClient'
import type { AdminEvidenceBurdenResponse } from '../types/adminEvidenceBurden'

const demoResult = (sessionId: string): AdminEvidenceBurdenResponse => ({
  sessionId, asOf: '2026-09-06T02:00:00Z', evidenceRequestCount: 1, repeatedRequestCount: 0, availableRequestCount: 0, requestableRequestCount: 0, consentRequiredRequestCount: 1, unavailableRequestCount: 0, submissionCount: 1, pendingSubmissionCount: 0, acceptedCount: 1, rejectedCount: 0, reviewRequiredCount: 0, unverifiedSubmissionCount: 0, failedQualityDimensionCount: 0, supplementalAssessmentCount: 1, resolutionCount: 1, latestResolutionStatus: 'RESOLVED', collectionStopped: true, maxRequestIteration: 1, measurementVersion: 'evidence-burden-metrics-v1', policyThresholdApplied: false, demoOnly: true,
  evidenceTypes: [{ evidenceType: 'CUSTOMER_SUBMITTED_RECENT_REVENUE_SUMMARY', sourceType: 'CUSTOMER_SUBMITTED', requestCount: 1, submissionCount: 1, acceptedCount: 1, rejectedCount: 0, reviewRequiredCount: 0, firstRequestedAt: '2026-09-06T01:20:00Z', lastRequestedAt: '2026-09-06T01:20:00Z' }],
})

export const mockAdminEvidenceBurdenProvider: AdminEvidenceBurdenProvider = {
  async get(sessionId, signal) {
    if (signal.aborted) throw new DOMException('Aborted', 'AbortError')
    return demoResult(sessionId)
  },
}
