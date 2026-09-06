import { describe, expect, it, vi } from 'vitest'
import type { AssessmentComparisonContext, AssessmentComparisonResponse } from '../types/assessmentComparison'
import { liveAssessmentComparisonProvider } from './assessmentComparisonClient'

const context: AssessmentComparisonContext = { baselineAssessmentId: 'asm_demo', supplementalAssessmentId: 'sam_demo', qualityCheckId: 'evq_demo' }
const response = { sessionId: 'ses_demo', comparison: null } satisfies AssessmentComparisonResponse

describe('liveAssessmentComparisonProvider', () => {
  it('loads and creates the session assessment comparison without a client decision payload', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => response })
    vi.stubGlobal('fetch', fetchMock)
    const signal = new AbortController().signal

    await liveAssessmentComparisonProvider.get('ses_demo', signal)
    await liveAssessmentComparisonProvider.compare('ses_demo', context, signal)

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/v1/sessions/ses_demo/assessment/comparison', { method: 'GET', signal })
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/v1/sessions/ses_demo/assessment/comparison', { method: 'POST', signal })
  })
})
