import type { ApiError } from '../types/api'
import type { ConsentListResponse, ConsentSourceType, ConsentState } from '../types/consent'

export interface ConsentProvider {
  list(sessionId: string, signal: AbortSignal): Promise<ConsentListResponse>
  grant(sessionId: string, sourceType: ConsentSourceType, signal: AbortSignal): Promise<ConsentState>
  withdraw(sessionId: string, sourceType: ConsentSourceType, signal: AbortSignal): Promise<ConsentState>
}

export const normalizeConsentError = (error: unknown): ApiError => {
  if (typeof error === 'object' && error !== null && 'code' in error && 'message' in error && 'retryable' in error) return error as ApiError
  return { code: 'CONSENT_REQUEST_FAILED', message: '데이터 이용 동의 상태를 확인하지 못했습니다.', retryable: true }
}

const request = async <T,>(url: string, signal: AbortSignal, method = 'GET'): Promise<T> => {
  const response = await fetch(url, { method, signal })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { error?: ApiError } | null
    throw body?.error ?? {
      code: 'CONSENT_REQUEST_FAILED',
      message: '데이터 이용 동의 요청에 실패했습니다.',
      requestId: response.headers.get('x-request-id') ?? undefined,
      retryable: response.status >= 500,
    } satisfies ApiError
  }
  return response.json() as Promise<T>
}

const consentUrl = (sessionId: string, suffix = '') => `/v1/sessions/${encodeURIComponent(sessionId)}/consents${suffix}`

export const liveConsentProvider: ConsentProvider = {
  list(sessionId, signal) {
    return request<ConsentListResponse>(consentUrl(sessionId), signal)
  },
  grant(sessionId, sourceType, signal) {
    return request<ConsentState>(consentUrl(sessionId, `/${encodeURIComponent(sourceType)}/grant`), signal, 'POST')
  },
  withdraw(sessionId, sourceType, signal) {
    return request<ConsentState>(consentUrl(sessionId, `/${encodeURIComponent(sourceType)}/withdraw`), signal, 'POST')
  },
}
