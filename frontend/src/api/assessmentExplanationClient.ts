import type { ApiError } from '../types/api'
import type { AssessmentExplanationResponse } from '../types/assessmentExplanation'

export interface AssessmentExplanationProvider {
  get(sessionId: string, signal: AbortSignal): Promise<AssessmentExplanationResponse>
  generate(sessionId: string, signal: AbortSignal): Promise<AssessmentExplanationResponse>
}

export const normalizeAssessmentExplanationError = (error: unknown): ApiError => {
  if (typeof error === 'object' && error !== null && 'code' in error && 'message' in error && 'retryable' in error) return error as ApiError
  return { code: 'ASSESSMENT_EXPLANATION_REQUEST_FAILED', message: '평가 결과 설명을 확인하지 못했습니다.', retryable: true }
}

const request = async (sessionId: string, signal: AbortSignal, method = 'GET'): Promise<AssessmentExplanationResponse> => {
  const suffix = method === 'POST' ? '/generate' : ''
  const response = await fetch(`/v1/sessions/${encodeURIComponent(sessionId)}/assessment/explanation${suffix}`, { method, signal })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { error?: ApiError } | null
    throw body?.error ?? {
      code: 'ASSESSMENT_EXPLANATION_REQUEST_FAILED',
      message: '평가 결과 설명 요청에 실패했습니다.',
      requestId: response.headers.get('x-request-id') ?? undefined,
      retryable: response.status >= 500,
    } satisfies ApiError
  }
  return response.json() as Promise<AssessmentExplanationResponse>
}

export const liveAssessmentExplanationProvider: AssessmentExplanationProvider = {
  get: (sessionId, signal) => request(sessionId, signal),
  generate: (sessionId, signal) => request(sessionId, signal, 'POST'),
}
