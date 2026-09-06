import { describe, expect, it, vi } from 'vitest'
import type { EvidenceResolutionContext, EvidenceResolutionResponse } from '../types/evidenceResolution'
import { liveEvidenceResolutionProvider } from './evidenceResolutionClient'

const context: EvidenceResolutionContext = { comparisonId: 'acp_demo', supplementalAssessmentId: 'sam_demo' }
const response = { sessionId: 'ses_demo', resolution: null } satisfies EvidenceResolutionResponse

describe('liveEvidenceResolutionProvider', () => {
  it('loads and resolves Evidence collection without a client decision payload', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => response })
    vi.stubGlobal('fetch', fetchMock)
    const signal = new AbortController().signal

    await liveEvidenceResolutionProvider.get('ses_demo', signal)
    await liveEvidenceResolutionProvider.resolve('ses_demo', context, signal)

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/v1/sessions/ses_demo/assessment/resolution', { method: 'GET', signal })
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/v1/sessions/ses_demo/assessment/resolution', { method: 'POST', signal })
  })
})
