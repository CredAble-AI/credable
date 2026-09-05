import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ConsentListResponse, ConsentState } from '../types/consent'
import { liveConsentProvider } from './consentClient'

const consent: ConsentState = {
  sourceType: 'BANK_INTERNAL',
  displayName: '은행 내부 데이터',
  description: '도입 은행이 보유한 고객·계좌·대출 관련 데이터',
  required: null,
  status: 'PENDING',
  grantedAt: null,
  withdrawnAt: null,
  updatedAt: null,
  scopeVersion: 'demo-consent-scopes-v1',
  demoOnly: true,
}

describe('liveConsentProvider', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('uses the session consent endpoints for list, grant, and withdraw', async () => {
    const listResponse: ConsentListResponse = {
      sessionId: 'ses_demo',
      consents: [consent],
      scopeVersion: 'demo-consent-scopes-v1',
      demoOnly: true,
    }
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => listResponse })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ ...consent, status: 'GRANTED' }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ ...consent, status: 'WITHDRAWN' }) })
    vi.stubGlobal('fetch', fetchMock)
    const signal = new AbortController().signal

    await liveConsentProvider.list('ses_demo', signal)
    await liveConsentProvider.grant('ses_demo', 'BANK_INTERNAL', signal)
    await liveConsentProvider.withdraw('ses_demo', 'BANK_INTERNAL', signal)

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/v1/sessions/ses_demo/consents', { method: 'GET', signal })
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/v1/sessions/ses_demo/consents/BANK_INTERNAL/grant', { method: 'POST', signal })
    expect(fetchMock).toHaveBeenNthCalledWith(3, '/v1/sessions/ses_demo/consents/BANK_INTERNAL/withdraw', { method: 'POST', signal })
  })
})
