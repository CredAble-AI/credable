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
})
