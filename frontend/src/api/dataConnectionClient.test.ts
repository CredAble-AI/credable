import { afterEach, describe, expect, it, vi } from 'vitest'
import type { DataSourceListResponse } from '../types/dataConnection'
import { liveDataConnectionProvider } from './dataConnectionClient'

const response: DataSourceListResponse = {
  sessionId: 'ses_demo',
  dataSources: [{
    sourceType: 'BANK_INTERNAL',
    displayName: '은행 내부 데이터',
    retrievalStatus: 'NOT_REQUESTED',
    verificationStatus: 'NOT_STARTED',
    observedAt: null,
    retrievedAt: null,
    dataVersion: null,
    reasonCode: null,
    demoOnly: true,
  }],
  demoOnly: true,
}

describe('liveDataConnectionProvider', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('uses the session data-source endpoints without adding client decisions', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => response })
      .mockResolvedValueOnce({ ok: true, json: async () => response })
    vi.stubGlobal('fetch', fetchMock)
    const signal = new AbortController().signal

    const listed = await liveDataConnectionProvider.list('ses_demo', signal)
    const refreshed = await liveDataConnectionProvider.refresh('ses_demo', signal)

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/v1/sessions/ses_demo/data-sources', { method: 'GET', signal })
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/v1/sessions/ses_demo/data-sources/refresh', { method: 'POST', signal })
    expect(listed).toEqual(response)
    expect(refreshed).toEqual(response)
    expect(listed).not.toHaveProperty('canProceed')
  })
})
