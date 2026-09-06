import type { ApiError } from '../types/api'
import type { SupplementalAssessmentResponse } from '../types/supplementalAssessment'

export interface SupplementalAssessmentProvider {
  get(sessionId: string, signal: AbortSignal): Promise<SupplementalAssessmentResponse>
  run(sessionId: string, submissionId: string, signal: AbortSignal): Promise<SupplementalAssessmentResponse>
}

export const normalizeSupplementalAssessmentError = (error: unknown): ApiError => {
  if (typeof error === 'object' && error !== null && 'code' in error && 'message' in error && 'retryable' in error) return error as ApiError
  return { code: 'SUPPLEMENTAL_ASSESSMENT_REQUEST_FAILED', message: '보완평가 상태를 확인하지 못했습니다.', retryable: true }
}

const request = async (url: string, signal: AbortSignal, init: RequestInit = {}): Promise<SupplementalAssessmentResponse> => {
  const response = await fetch(url, { ...init, signal })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { error?: ApiError } | null
    throw body?.error ?? { code: 'SUPPLEMENTAL_ASSESSMENT_REQUEST_FAILED', message: '보완평가 요청에 실패했습니다.', requestId: response.headers.get('x-request-id') ?? undefined, retryable: response.status >= 500 } satisfies ApiError
  }
  return response.json() as Promise<SupplementalAssessmentResponse>
}

const assessmentUrl = (sessionId: string, suffix = '') => `/v1/sessions/${encodeURIComponent(sessionId)}/assessment/supplemental${suffix}`

export const liveSupplementalAssessmentProvider: SupplementalAssessmentProvider = {
  get: (sessionId, signal) => request(assessmentUrl(sessionId), signal),
  run: (sessionId, submissionId, signal) => request(assessmentUrl(sessionId, '/run'), signal, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ submissionId }) }),
}
