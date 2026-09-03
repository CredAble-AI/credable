import type { ApiError, CheckEligibilityRequest, EligibilityResult, SecondLookCase } from '../types/case'

export interface EligibilityProvider {
  getCase(caseId: string, signal: AbortSignal): Promise<SecondLookCase>
  check(request: CheckEligibilityRequest, signal: AbortSignal): Promise<EligibilityResult>
}

const request = async <T>(url: string, init: RequestInit, fallbackMessage: string): Promise<T> => {
  const response = await fetch(url, init)
  if (!response.ok) {
    throw {
      code: 'ELIGIBILITY_REQUEST_FAILED',
      message: fallbackMessage,
      requestId: response.headers.get('x-request-id') ?? undefined,
      retryable: response.status >= 500,
    } satisfies ApiError
  }
  return response.json() as Promise<T>
}

export const normalizeEligibilityError = (error: unknown): ApiError => {
  if (typeof error === 'object' && error !== null && 'code' in error && 'message' in error && 'retryable' in error) return error as ApiError
  return { code: 'ELIGIBILITY_REQUEST_FAILED', message: '재심사 진입 가능성을 확인하지 못했습니다.', retryable: true }
}

export const liveEligibilityProvider: EligibilityProvider = {
  getCase: (caseId, signal) => request(`/v1/cases/${encodeURIComponent(caseId)}`, { signal }, 'Case 정보를 불러오지 못했습니다.'),
  check: (body, signal) => request('/v1/eligibility/check', { method: 'POST', signal, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }, 'Eligibility 확인 요청에 실패했습니다.'),
}
