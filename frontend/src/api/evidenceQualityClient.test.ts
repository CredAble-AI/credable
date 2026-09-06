import { describe, expect, it, vi } from 'vitest'
import type { EvidenceQualityResponse } from '../types/evidenceQuality'
import { liveEvidenceQualityProvider } from './evidenceQualityClient'

const response = { sessionId: 'ses_demo', quality: null } satisfies EvidenceQualityResponse

describe('liveEvidenceQualityProvider', () => {
  it('uses the submission-scoped GET and POST quality endpoints', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => response })
    vi.stubGlobal('fetch', fetchMock)
    const signal = new AbortController().signal

    await liveEvidenceQualityProvider.get('ses_demo', 'sub_demo', signal)
    await liveEvidenceQualityProvider.check('ses_demo', 'sub_demo', signal)

    const url = '/v1/sessions/ses_demo/evidence/submissions/sub_demo/quality'
    expect(fetchMock).toHaveBeenNthCalledWith(1, url, { method: 'GET', signal })
    expect(fetchMock).toHaveBeenNthCalledWith(2, url, { method: 'POST', signal })
  })
})
