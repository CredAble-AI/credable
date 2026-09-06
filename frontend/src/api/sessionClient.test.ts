import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { liveCustomerSessionProvider } from './sessionClient'

describe('liveCustomerSessionProvider', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.unstubAllGlobals())

  it('creates a demo session with only businessBorrowerType', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        sessionId: 'ses_sole_proprietor',
        session: {
          sessionId: 'ses_sole_proprietor',
          demoProfile: {
            demoProfileId: 'small-business',
            businessBorrowerType: 'SOLE_PROPRIETOR',
            displayName: '개인사업자',
            description: '개업 초기 소상공인을 예시로 한 개인사업자 합성 Demo 사례',
          },
          status: 'CREATED',
          createdAt: '2026-09-06T00:00:00+09:00',
          dataVersion: 'demo-profiles-v3',
          demoOnly: true,
        },
      }),
    })
    vi.stubGlobal('fetch', fetchMock)

    const session = await liveCustomerSessionProvider.create('SOLE_PROPRIETOR', new AbortController().signal)

    expect(fetchMock).toHaveBeenCalledWith('/v1/sessions/demo', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ businessBorrowerType: 'SOLE_PROPRIETOR' }),
    }))
    expect(session.demoProfile.businessBorrowerType).toBe('SOLE_PROPRIETOR')
    expect(localStorage.getItem('credable.session-id')).toBe('ses_sole_proprietor')
  })

  it('clears the stored session only when the server returns not found', async () => {
    localStorage.setItem('credable.session-id', 'ses_expired')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      headers: { get: () => 'req_not_found' },
      json: async () => ({ error: { code: 'CUSTOMER_SESSION_NOT_FOUND', message: '세션을 찾을 수 없습니다.', requestId: 'req_not_found', retryable: false } }),
    }))

    await expect(liveCustomerSessionProvider.get(new AbortController().signal)).resolves.toBeNull()
    expect(localStorage.getItem('credable.session-id')).toBeNull()
  })

  it('keeps the stored session when recovery fails temporarily', async () => {
    localStorage.setItem('credable.session-id', 'ses_retryable')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      headers: { get: () => 'req_unavailable' },
      json: async () => ({ error: { code: 'SESSION_SERVICE_UNAVAILABLE', message: '세션 서비스를 사용할 수 없습니다.', requestId: 'req_unavailable', retryable: true } }),
    }))

    await expect(liveCustomerSessionProvider.get(new AbortController().signal)).rejects.toMatchObject({
      code: 'SESSION_SERVICE_UNAVAILABLE',
      requestId: 'req_unavailable',
      retryable: true,
    })
    expect(localStorage.getItem('credable.session-id')).toBe('ses_retryable')
  })

  it('keeps the stored session when the network request fails', async () => {
    localStorage.setItem('credable.session-id', 'ses_offline')
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    await expect(liveCustomerSessionProvider.get(new AbortController().signal)).rejects.toMatchObject({
      code: 'SESSION_REQUEST_FAILED',
      retryable: true,
    })
    expect(localStorage.getItem('credable.session-id')).toBe('ses_offline')
  })
})
