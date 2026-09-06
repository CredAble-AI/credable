import { describe, expect, it, vi } from 'vitest'
import type { AdminReviewDetailResponse, AdminReviewQueueResponse } from '../types/adminReview'
import { liveAdminReviewProvider } from './adminReviewClient'

const response: AdminReviewQueueResponse = { totalCount: 0, limit: 20, offset: 0, items: [], demoOnly: true }
const detail: AdminReviewDetailResponse = { review: { reviewId: 'uwr_demo', sessionId: 'ses_demo', triggerType: 'CUSTOMER_ASSESSMENT_REVIEW', triggerId: 'arr_demo', targetType: 'SUPPLEMENTAL_ASSESSMENT', targetAssessmentId: 'sam_demo', reasonCodes: ['CUSTOMER_REQUESTED_ASSESSMENT_REVIEW'], requestedAt: '2026-09-06T02:00:00Z', dataVersion: 'demo-v1', policyVersion: 'assessment-review-request-policy-v1', status: 'IN_REVIEW', demoOnly: true }, context: { assessment: null, boundaryCheck: null, selection: null, submission: null, quality: null, supplementalAssessment: null, comparison: null, resolution: null } }

describe('liveAdminReviewProvider', () => {
  it('loads a filtered review page without authentication headers', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => response })
    vi.stubGlobal('fetch', fetchMock)
    const signal = new AbortController().signal

    await liveAdminReviewProvider.list({ limit: 20, offset: 0, status: 'PENDING' }, signal)

    expect(fetchMock).toHaveBeenCalledWith('/v1/admin/underwriter-reviews?limit=20&offset=0&status=PENDING', { method: 'GET', signal })
  })

  it('preserves structured server errors', async () => {
    const error = { code: 'UNDERWRITER_REVIEW_STORE_UNAVAILABLE', message: '검토 목록을 확인할 수 없습니다.', requestId: 'req_demo', retryable: true }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 503, headers: new Headers(), json: async () => ({ error }) }))

    await expect(liveAdminReviewProvider.list({ limit: 20, offset: 0, status: null }, new AbortController().signal)).rejects.toEqual(error)
  })

  it('loads and claims one encoded review without a request body', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => detail })
    vi.stubGlobal('fetch', fetchMock)
    const signal = new AbortController().signal

    await liveAdminReviewProvider.get('uwr/demo', signal)
    await liveAdminReviewProvider.claim('uwr/demo', signal)

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/v1/admin/underwriter-reviews/uwr%2Fdemo', { method: 'GET', signal })
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/v1/admin/underwriter-reviews/uwr%2Fdemo/claim', { method: 'POST', signal })
  })

  it('completes a review with the selected result code and the decision reason', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => detail })
    vi.stubGlobal('fetch', fetchMock)
    const signal = new AbortController().signal

    await liveAdminReviewProvider.complete('uwr_demo', 'ASSESSMENT_CONFIRMED', '서버 기록과 일치해 기존 평가를 유지합니다.', signal)

    expect(fetchMock).toHaveBeenCalledWith('/v1/admin/underwriter-reviews/uwr_demo/complete', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ resultCode: 'ASSESSMENT_CONFIRMED', decisionNote: '서버 기록과 일치해 기존 평가를 유지합니다.' }), signal })
  })
})
