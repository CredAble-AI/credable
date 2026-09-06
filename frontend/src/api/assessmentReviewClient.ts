import type { ApiError } from '../types/api'
import type { AssessmentReviewRequestResponse } from '../types/assessmentReview'

export interface AssessmentReviewProvider {
  get(sessionId: string, signal: AbortSignal): Promise<AssessmentReviewRequestResponse>
  request(sessionId: string, signal: AbortSignal): Promise<AssessmentReviewRequestResponse>
}

export const normalizeAssessmentReviewError = (error: unknown): ApiError => {
  if (typeof error === 'object' && error !== null && 'code' in error && 'message' in error && 'retryable' in error) return error as ApiError
  return { code: 'ASSESSMENT_REVIEW_REQUEST_FAILED', message: '평가 재확인 요청 상태를 확인하지 못했습니다.', retryable: true }
}

const send = async (sessionId: string, signal: AbortSignal, method = 'GET'): Promise<AssessmentReviewRequestResponse> => {
  const response = await fetch(`/v1/sessions/${encodeURIComponent(sessionId)}/assessment/review-request`, { method, signal })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { error?: ApiError } | null
    throw body?.error ?? { code: 'ASSESSMENT_REVIEW_REQUEST_FAILED', message: '평가 재확인 요청에 실패했습니다.', requestId: response.headers.get('x-request-id') ?? undefined, retryable: response.status >= 500 } satisfies ApiError
  }
  return response.json() as Promise<AssessmentReviewRequestResponse>
}

export const liveAssessmentReviewProvider: AssessmentReviewProvider = {
  get: (sessionId, signal) => send(sessionId, signal),
  request: (sessionId, signal) => send(sessionId, signal, 'POST'),
}
