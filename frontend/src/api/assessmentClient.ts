import type { ApiError } from '../types/api'
import type { AssessmentRequest, AssessmentResponse, AssessmentResult } from '../types/assessment'

export interface AssessmentProvider {
  get(request: AssessmentRequest, signal: AbortSignal): Promise<AssessmentResult>
  run(request: AssessmentRequest, signal: AbortSignal): Promise<AssessmentResult>
}

export const normalizeAssessmentError = (error: unknown): ApiError => {
  if (typeof error === 'object' && error !== null && 'code' in error && 'message' in error && 'retryable' in error) return error as ApiError
  return { code: 'ASSESSMENT_REQUEST_FAILED', message: '보완 평가 결과를 확인하지 못했습니다.', retryable: true }
}

const isResponse = (value: unknown): value is AssessmentResponse => {
  if (!value || typeof value !== 'object') return false
  const response = value as Partial<AssessmentResponse>
  const statuses = new Set(['NOT_RUN', 'MODEL_NOT_CONFIGURED', 'COMPLETED', 'INSUFFICIENT_DATA', 'UNSUPPORTED_CUSTOMER_TYPE', 'FAILED'])
  return typeof response.sessionId === 'string'
    && Boolean(response.assessment && statuses.has(response.assessment.status))
    && response.assessment?.demoOnly === true
}

const requestAssessment = async (url: string, signal: AbortSignal, method = 'GET'): Promise<AssessmentResult> => {
  const response = await fetch(url, { method, signal })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { error?: ApiError } | null
    throw body?.error ?? { code: 'ASSESSMENT_REQUEST_FAILED', message: '보완 평가 요청에 실패했습니다.', requestId: response.headers.get('x-request-id') ?? undefined, retryable: response.status >= 500 } satisfies ApiError
  }
  const body: unknown = await response.json().catch(() => null)
  if (!isResponse(body)) throw { code: 'ASSESSMENT_RESPONSE_INVALID', message: '보완 평가 응답 형식을 확인할 수 없습니다.', retryable: false } satisfies ApiError
  return { ...body, dataSummary: [], excludedData: [], canProceed: null, proceedReason: '상품 비교 진행 여부는 Backend 계약 확정 후 제공됩니다.', resultMode: 'LIVE' }
}

export const liveAssessmentProvider: AssessmentProvider = {
  get({ sessionId }, signal) { return requestAssessment(`/v1/sessions/${encodeURIComponent(sessionId)}/assessment`, signal) },
  run({ sessionId }, signal) { return requestAssessment(`/v1/sessions/${encodeURIComponent(sessionId)}/assessment/run`, signal, 'POST') },
}
