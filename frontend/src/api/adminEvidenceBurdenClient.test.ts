import { describe, expect, it, vi } from 'vitest'
import type { AdminEvidenceBurdenResponse } from '../types/adminEvidenceBurden'
import { liveAdminEvidenceBurdenProvider } from './adminEvidenceBurdenClient'

const response: AdminEvidenceBurdenResponse = { sessionId: 'ses_demo', asOf: '2026-09-06T02:00:00Z', evidenceRequestCount: 0, repeatedRequestCount: 0, availableRequestCount: 0, requestableRequestCount: 0, consentRequiredRequestCount: 0, unavailableRequestCount: 0, submissionCount: 0, pendingSubmissionCount: 0, acceptedCount: 0, rejectedCount: 0, reviewRequiredCount: 0, unverifiedSubmissionCount: 0, failedQualityDimensionCount: 0, supplementalAssessmentCount: 0, resolutionCount: 0, latestResolutionStatus: null, collectionStopped: null, maxRequestIteration: 0, evidenceTypes: [], measurementVersion: 'evidence-burden-metrics-v1', policyThresholdApplied: false, demoOnly: true }

describe('liveAdminEvidenceBurdenProvider', () => {
  it('sends the administrator key only in the request header', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => response })
    vi.stubGlobal('fetch', fetchMock)
    const signal = new AbortController().signal

    await liveAdminEvidenceBurdenProvider.get('demo-secret', 'ses/demo', signal)

    expect(fetchMock).toHaveBeenCalledWith('/v1/admin/sessions/ses%2Fdemo/evidence-burden', { method: 'GET', headers: { 'X-Admin-API-Key': 'demo-secret' }, signal })
    expect(fetchMock.mock.calls[0][0]).not.toContain('demo-secret')
  })

  it('preserves structured lineage errors', async () => {
    const error = { code: 'EVIDENCE_BURDEN_LINEAGE_INVALID', message: '연결된 이력이 필요합니다.', requestId: 'req_demo', retryable: false }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 409, headers: new Headers(), json: async () => ({ error }) }))

    await expect(liveAdminEvidenceBurdenProvider.get('demo-secret', 'ses_demo', new AbortController().signal)).rejects.toEqual(error)
  })
})
