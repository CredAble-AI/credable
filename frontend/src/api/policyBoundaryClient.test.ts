import { afterEach, describe, expect, it, vi } from 'vitest'
import type { PolicyBoundaryCheckResponse } from '../types/policyBoundary'
import { livePolicyBoundaryProvider } from './policyBoundaryClient'

const response: PolicyBoundaryCheckResponse = { sessionId: 'ses_demo', boundaryCheck: null }

describe('livePolicyBoundaryProvider', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('uses the policy boundary recovery and check endpoints', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => response })
      .mockResolvedValueOnce({ ok: true, json: async () => response })
    vi.stubGlobal('fetch', fetchMock)
    const signal = new AbortController().signal

    const recovered = await livePolicyBoundaryProvider.get('ses_demo', signal)
    const checked = await livePolicyBoundaryProvider.check('ses_demo', signal)

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/v1/sessions/ses_demo/assessment/boundary-check', { method: 'GET', signal })
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/v1/sessions/ses_demo/assessment/boundary-check', { method: 'POST', signal })
    expect(recovered).toEqual(response)
    expect(checked).toEqual(response)
  })
})
