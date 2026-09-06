import { describe, expect, it, vi } from 'vitest'
import type { EvidenceConsentResponse } from '../types/evidenceConsent'
import { liveEvidenceConsentProvider } from './evidenceConsentClient'

const response = { sessionId: 'ses_demo', selectionId: 'evs_demo' } as EvidenceConsentResponse

describe('liveEvidenceConsentProvider', () => {
  it('loads the consent attached to the selected Evidence', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => response })
    vi.stubGlobal('fetch', fetchMock)
    const signal = new AbortController().signal

    await liveEvidenceConsentProvider.get('ses_demo', 'evs_demo', signal)

    expect(fetchMock).toHaveBeenCalledWith('/v1/sessions/ses_demo/evidence/selections/evs_demo/consent', { method: 'GET', signal })
  })

  it('posts grant and withdraw actions to the selection-scoped endpoints', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => response })
    vi.stubGlobal('fetch', fetchMock)
    const signal = new AbortController().signal

    await liveEvidenceConsentProvider.grant('ses_demo', 'evs_demo', signal)
    await liveEvidenceConsentProvider.withdraw('ses_demo', 'evs_demo', signal)

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/v1/sessions/ses_demo/evidence/selections/evs_demo/consent/grant', { method: 'POST', signal })
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/v1/sessions/ses_demo/evidence/selections/evs_demo/consent/withdraw', { method: 'POST', signal })
  })
})
