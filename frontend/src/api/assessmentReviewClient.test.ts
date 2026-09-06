import { describe, expect, it, vi } from 'vitest'
import type { AssessmentReviewRequestResponse } from '../types/assessmentReview'
import { liveAssessmentReviewProvider } from './assessmentReviewClient'

const response: AssessmentReviewRequestResponse = { sessionId: 'ses_demo', reviewRequest: null, underwriterReviewId: null, processing: null }

describe('liveAssessmentReviewProvider', () => {
  it.each([['get', 'GET'], ['request', 'POST']] as const)('uses %s with the expected method', async (operation, method) => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => response })
    vi.stubGlobal('fetch', fetchMock)
    const signal = new AbortController().signal

    await liveAssessmentReviewProvider[operation]('ses_demo', signal)

    expect(fetchMock).toHaveBeenCalledWith('/v1/sessions/ses_demo/assessment/review-request', { method, signal })
  })
})
