import { describe, expect, it, vi } from 'vitest'
import type { AdminReviewDetailResponse, AdminReviewQueueResponse } from '../types/adminReview'
import { liveAdminReviewProvider } from './adminReviewClient'

const response: AdminReviewQueueResponse = { totalCount: 0, limit: 20, offset: 0, items: [], demoOnly: true }
const detail: AdminReviewDetailResponse = { review: { reviewId: 'uwr_demo', sessionId: 'ses_demo', triggerType: 'CUSTOMER_ASSESSMENT_REVIEW', triggerId: 'arr_demo', targetType: 'SUPPLEMENTAL_ASSESSMENT', targetAssessmentId: 'sam_demo', reasonCodes: ['CUSTOMER_REQUESTED_ASSESSMENT_REVIEW'], requestedAt: '2026-09-06T02:00:00Z', dataVersion: 'demo-v1', policyVersion: 'assessment-review-request-policy-v1', status: 'IN_REVIEW', demoOnly: true } }

describe('liveAdminReviewProvider', () => {
  it('sends the administrator key only in the request header', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => response })
    vi.stubGlobal('fetch', fetchMock)
    const signal = new AbortController().signal

    await liveAdminReviewProvider.list('demo-secret', { limit: 20, offset: 0, status: 'PENDING' }, signal)

    expect(fetchMock).toHaveBeenCalledWith('/v1/admin/underwriter-reviews?limit=20&offset=0&status=PENDING', { method: 'GET', headers: { 'X-Admin-API-Key': 'demo-secret' }, signal })
    expect(fetchMock.mock.calls[0][0]).not.toContain('demo-secret')
  })

  it('preserves the structured authentication error', async () => {
    const error = { code: 'ADMIN_AUTHENTICATION_FAILED', message: '관리자 인증에 실패했습니다.', requestId: 'req_demo', retryable: false }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 401, headers: new Headers(), json: async () => ({ error }) }))

    await expect(liveAdminReviewProvider.list('wrong-key', { limit: 20, offset: 0, status: null }, new AbortController().signal)).rejects.toEqual(error)
  })

  it('loads and claims one encoded review without a request body', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => detail })
    vi.stubGlobal('fetch', fetchMock)
    const signal = new AbortController().signal

    await liveAdminReviewProvider.get('demo-secret', 'uwr/demo', signal)
    await liveAdminReviewProvider.claim('demo-secret', 'uwr/demo', signal)

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/v1/admin/underwriter-reviews/uwr%2Fdemo', { method: 'GET', headers: { 'X-Admin-API-Key': 'demo-secret' }, signal })
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/v1/admin/underwriter-reviews/uwr%2Fdemo/claim', { method: 'POST', headers: { 'X-Admin-API-Key': 'demo-secret' }, signal })
  })

  it('completes a review with the selected backend result code', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => detail })
    vi.stubGlobal('fetch', fetchMock)
    const signal = new AbortController().signal

    await liveAdminReviewProvider.complete('demo-secret', 'uwr_demo', 'ASSESSMENT_CONFIRMED', signal)

    expect(fetchMock).toHaveBeenCalledWith('/v1/admin/underwriter-reviews/uwr_demo/complete', { method: 'POST', headers: { 'X-Admin-API-Key': 'demo-secret', 'Content-Type': 'application/json' }, body: JSON.stringify({ resultCode: 'ASSESSMENT_CONFIRMED' }), signal })
  })
})
