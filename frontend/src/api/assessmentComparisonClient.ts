import type { ApiError } from '../types/api'
import type { AssessmentComparisonContext, AssessmentComparisonResponse } from '../types/assessmentComparison'

export interface AssessmentComparisonProvider {
  get(sessionId: string, signal: AbortSignal): Promise<AssessmentComparisonResponse>
  compare(sessionId: string, context: AssessmentComparisonContext, signal: AbortSignal): Promise<AssessmentComparisonResponse>
}

export const normalizeAssessmentComparisonError = (error: unknown): ApiError => {
  if (typeof error === 'object' && error !== null && 'code' in error && 'message' in error && 'retryable' in error) return error as ApiError
  return { code: 'ASSESSMENT_COMPARISON_REQUEST_FAILED', message: '평가 전후 비교 상태를 확인하지 못했습니다.', retryable: true }
}

const request = async (sessionId: string, signal: AbortSignal, method = 'GET'): Promise<AssessmentComparisonResponse> => {
  const response = await fetch(`/v1/sessions/${encodeURIComponent(sessionId)}/assessment/comparison`, { method, signal })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { error?: ApiError } | null
    throw body?.error ?? { code: 'ASSESSMENT_COMPARISON_REQUEST_FAILED', message: '평가 전후 비교 요청에 실패했습니다.', requestId: response.headers.get('x-request-id') ?? undefined, retryable: response.status >= 500 } satisfies ApiError
  }
  return response.json() as Promise<AssessmentComparisonResponse>
}

export const liveAssessmentComparisonProvider: AssessmentComparisonProvider = {
  get: (sessionId, signal) => request(sessionId, signal),
  compare: (sessionId, _context, signal) => request(sessionId, signal, 'POST'),
}
