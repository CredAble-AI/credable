import { describe, expect, it, vi } from 'vitest'
import type { AssessmentExplanationResponse } from '../types/assessmentExplanation'
import { liveAssessmentExplanationProvider } from './assessmentExplanationClient'

const response = { sessionId: 'ses_demo', explanation: null } satisfies AssessmentExplanationResponse

describe('liveAssessmentExplanationProvider', () => {
  it('loads and explicitly generates an explanation without a client decision payload', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => response })
    vi.stubGlobal('fetch', fetchMock)
    const signal = new AbortController().signal

    await liveAssessmentExplanationProvider.get('ses_demo', signal)
    await liveAssessmentExplanationProvider.generate('ses_demo', signal)

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/v1/sessions/ses_demo/assessment/explanation', { method: 'GET', signal })
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/v1/sessions/ses_demo/assessment/explanation/generate', { method: 'POST', signal })
  })
})
