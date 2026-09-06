import { describe, expect, it, vi } from 'vitest'
import type { SupplementalAssessmentResponse } from '../types/supplementalAssessment'
import { liveSupplementalAssessmentProvider } from './supplementalAssessmentClient'

const response = { sessionId: 'ses_demo', supplementalAssessment: null } satisfies SupplementalAssessmentResponse

describe('liveSupplementalAssessmentProvider', () => {
  it('loads and runs the session supplemental assessment with the submission id', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => response })
    vi.stubGlobal('fetch', fetchMock)
    const signal = new AbortController().signal

    await liveSupplementalAssessmentProvider.get('ses_demo', signal)
    await liveSupplementalAssessmentProvider.run('ses_demo', 'sub_demo', signal)

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/v1/sessions/ses_demo/assessment/supplemental', { signal })
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/v1/sessions/ses_demo/assessment/supplemental/run', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ submissionId: 'sub_demo' }), signal })
  })
})
