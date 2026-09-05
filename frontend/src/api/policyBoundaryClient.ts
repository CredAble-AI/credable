import type { ApiError } from '../types/api'
import type { PolicyBoundaryCheckResponse } from '../types/policyBoundary'

export interface PolicyBoundaryProvider {
  get(sessionId: string, signal: AbortSignal): Promise<PolicyBoundaryCheckResponse>
  check(sessionId: string, signal: AbortSignal): Promise<PolicyBoundaryCheckResponse>
}

export const normalizePolicyBoundaryError = (error: unknown): ApiError => {
  if (typeof error === 'object' && error !== null && 'code' in error && 'message' in error && 'retryable' in error) return error as ApiError
  return { code: 'POLICY_BOUNDARY_REQUEST_FAILED', message: '정책 경계 상태를 확인하지 못했습니다.', retryable: true }
}

const requestBoundary = async (url: string, signal: AbortSignal, method = 'GET'): Promise<PolicyBoundaryCheckResponse> => {
  const response = await fetch(url, { method, signal })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { error?: ApiError } | null
    throw body?.error ?? {
      code: 'POLICY_BOUNDARY_REQUEST_FAILED',
      message: '정책 경계 확인 요청에 실패했습니다.',
      requestId: response.headers.get('x-request-id') ?? undefined,
      retryable: response.status >= 500,
    } satisfies ApiError
  }
  return response.json() as Promise<PolicyBoundaryCheckResponse>
}

const boundaryUrl = (sessionId: string) => `/v1/sessions/${encodeURIComponent(sessionId)}/assessment/boundary-check`

export const livePolicyBoundaryProvider: PolicyBoundaryProvider = {
  get(sessionId, signal) {
    return requestBoundary(boundaryUrl(sessionId), signal)
  },
  check(sessionId, signal) {
    return requestBoundary(boundaryUrl(sessionId), signal, 'POST')
  },
}
