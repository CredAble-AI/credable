import { afterEach, describe, expect, it, vi } from 'vitest'
import type { EvidenceSelectionResponse } from '../types/evidenceSelection'
import { liveEvidenceSelectionProvider } from './evidenceSelectionClient'

const response: EvidenceSelectionResponse = { sessionId: 'ses_demo', selection: null }

describe('liveEvidenceSelectionProvider', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('uses the session Evidence recovery and selection endpoints', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => response })
      .mockResolvedValueOnce({ ok: true, json: async () => response })
    vi.stubGlobal('fetch', fetchMock)
    const signal = new AbortController().signal

    expect(await liveEvidenceSelectionProvider.get('ses_demo', signal)).toEqual(response)
    expect(await liveEvidenceSelectionProvider.selectNext('ses_demo', signal)).toEqual(response)
    expect(fetchMock).toHaveBeenNthCalledWith(1, '/v1/sessions/ses_demo/evidence/next', { method: 'GET', signal })
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/v1/sessions/ses_demo/evidence/next', { method: 'POST', signal })
  })
})
