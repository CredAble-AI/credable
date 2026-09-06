import { describe, expect, it, vi } from 'vitest'
import type { AssessmentReviewRequestResponse } from '../types/assessmentReview'
import { liveAssessmentReviewProvider } from './assessmentReviewClient'

const response: AssessmentReviewRequestResponse = { sessionId: 'ses_demo', reviewRequest: null, underwriterReviewId: null, processing: null }

describe('liveAssessmentReviewProvider', () => {
  it('reads the current request without creating one', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => response })
    vi.stubGlobal('fetch', fetchMock)
    const signal = new AbortController().signal

    await liveAssessmentReviewProvider.get('ses_demo', signal)

    expect(fetchMock).toHaveBeenCalledWith('/v1/sessions/ses_demo/assessment/review-request', { method: 'GET', signal })
  })

  it('sends the customer reason with a new request', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => response })
    vi.stubGlobal('fetch', fetchMock)
    const signal = new AbortController().signal

    await liveAssessmentReviewProvider.request('ses_demo', 'INCORRECT_INFORMATION', signal)

    expect(fetchMock).toHaveBeenCalledWith('/v1/sessions/ses_demo/assessment/review-request', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ customerReasonCode: 'INCORRECT_INFORMATION' }),
      signal,
    })
  })
})
