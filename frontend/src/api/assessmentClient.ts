import type { ApiError } from '../types/api'
import type { AssessmentRequest, AssessmentResponse } from '../types/assessment'

export interface AssessmentProvider {
  get(request: AssessmentRequest, signal: AbortSignal): Promise<AssessmentResponse>
  run(request: AssessmentRequest, signal: AbortSignal): Promise<AssessmentResponse>
}

export const normalizeAssessmentError = (error: unknown): ApiError => {
  if (typeof error === 'object' && error !== null && 'code' in error && 'message' in error && 'retryable' in error) return error as ApiError
  return { code: 'ASSESSMENT_REQUEST_FAILED', message: '기준평가 상태를 확인하지 못했습니다.', retryable: true }
}

const requestAssessment = async (url: string, signal: AbortSignal, method = 'GET'): Promise<AssessmentResponse> => {
  const response = await fetch(url, { method, signal })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { error?: ApiError } | null
    throw body?.error ?? {
      code: 'ASSESSMENT_REQUEST_FAILED',
      message: '기준평가 요청에 실패했습니다.',
      requestId: response.headers.get('x-request-id') ?? undefined,
      retryable: response.status >= 500,
    } satisfies ApiError
  }
  return response.json() as Promise<AssessmentResponse>
}

export const liveAssessmentProvider: AssessmentProvider = {
  get({ sessionId }, signal) {
    return requestAssessment(`/v1/sessions/${encodeURIComponent(sessionId)}/assessment`, signal)
  },
  run({ sessionId }, signal) {
    return requestAssessment(`/v1/sessions/${encodeURIComponent(sessionId)}/assessment/run`, signal, 'POST')
  },
}
