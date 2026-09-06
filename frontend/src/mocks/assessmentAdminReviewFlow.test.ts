import { describe, expect, it } from 'vitest'
import { mockAdminReviewProvider } from './adminReviewProvider'
import { mockAssessmentReviewProvider } from './assessmentReviewProvider'

describe('mock assessment and underwriter review flow', () => {
  it('shares one review state from customer request through underwriter completion', async () => {
    const signal = new AbortController().signal
    const sessionId = 'ses_mock_linkage_test'

    const requested = await mockAssessmentReviewProvider.request(sessionId, 'INCORRECT_INFORMATION', signal)
    const reviewId = requested.underwriterReviewId!
    expect((await mockAdminReviewProvider.get(reviewId, signal)).review.status).toBe('PENDING')

    await mockAdminReviewProvider.claim(reviewId, signal)
    expect((await mockAssessmentReviewProvider.get(sessionId, signal)).processing?.status).toBe('IN_REVIEW')

    await mockAdminReviewProvider.complete(reviewId, 'ASSESSMENT_CONFIRMED', '합성 시연 데이터로 확인했습니다.', signal)
    const completed = await mockAssessmentReviewProvider.get(sessionId, signal)
    expect(completed.processing?.status).toBe('COMPLETED')
    expect(completed.processing?.resultCode).toBe('ASSESSMENT_CONFIRMED')
  })
})
