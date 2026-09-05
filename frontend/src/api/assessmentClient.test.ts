import { afterEach, describe, expect, it, vi } from 'vitest'
import type { AssessmentResponse } from '../types/assessment'
import { liveAssessmentProvider } from './assessmentClient'

const response: AssessmentResponse = {
  sessionId: 'ses_demo',
  assessment: {
    assessmentId: null,
    status: 'NOT_RUN',
    calculatedAt: null,
    inputSnapshotId: null,
    modelVersion: null,
    reasonCode: null,
    uncertainty: null,
    demoOnly: true,
  },
}

describe('liveAssessmentProvider', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('uses the session assessment endpoints and preserves the server response', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => response })
      .mockResolvedValueOnce({ ok: true, json: async () => response })
    vi.stubGlobal('fetch', fetchMock)
    const signal = new AbortController().signal
    const request = { sessionId: 'ses_demo', profileType: 'small-business' }

    const recovered = await liveAssessmentProvider.get(request, signal)
    const executed = await liveAssessmentProvider.run(request, signal)

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/v1/sessions/ses_demo/assessment', { method: 'GET', signal })
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/v1/sessions/ses_demo/assessment/run', { method: 'POST', signal })
    expect(recovered).toEqual(response)
    expect(executed).toEqual(response)
    expect(recovered).not.toHaveProperty('canProceed')
    expect(recovered).not.toHaveProperty('summary')
  })
})
