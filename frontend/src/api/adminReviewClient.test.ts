import { describe, expect, it, vi } from 'vitest'
import type { AdminReviewQueueResponse } from '../types/adminReview'
import { liveAdminReviewProvider } from './adminReviewClient'

const response: AdminReviewQueueResponse = { totalCount: 0, limit: 20, offset: 0, items: [], demoOnly: true }

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
})
