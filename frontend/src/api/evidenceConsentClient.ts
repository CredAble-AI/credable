import type { ApiError } from '../types/api'
import type { EvidenceConsentResponse } from '../types/evidenceConsent'

export interface EvidenceConsentProvider {
  get(sessionId: string, selectionId: string, signal: AbortSignal): Promise<EvidenceConsentResponse>
  grant(sessionId: string, selectionId: string, signal: AbortSignal): Promise<EvidenceConsentResponse>
  withdraw(sessionId: string, selectionId: string, signal: AbortSignal): Promise<EvidenceConsentResponse>
}

export const normalizeEvidenceConsentError = (error: unknown): ApiError => {
  if (typeof error === 'object' && error !== null && 'code' in error && 'message' in error && 'retryable' in error) return error as ApiError
  return { code: 'EVIDENCE_CONSENT_REQUEST_FAILED', message: '선택한 증빙의 이용 동의 상태를 확인하지 못했습니다.', retryable: true }
}

const request = async (url: string, signal: AbortSignal, method = 'GET'): Promise<EvidenceConsentResponse> => {
  const response = await fetch(url, { method, signal })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { error?: ApiError } | null
    throw body?.error ?? {
      code: 'EVIDENCE_CONSENT_REQUEST_FAILED',
      message: '선택한 증빙의 이용 동의 요청에 실패했습니다.',
      requestId: response.headers.get('x-request-id') ?? undefined,
      retryable: response.status >= 500,
    } satisfies ApiError
  }
  return response.json() as Promise<EvidenceConsentResponse>
}

const consentUrl = (sessionId: string, selectionId: string, action = '') => `/v1/sessions/${encodeURIComponent(sessionId)}/evidence/selections/${encodeURIComponent(selectionId)}/consent${action}`

export const liveEvidenceConsentProvider: EvidenceConsentProvider = {
  get: (sessionId, selectionId, signal) => request(consentUrl(sessionId, selectionId), signal),
  grant: (sessionId, selectionId, signal) => request(consentUrl(sessionId, selectionId, '/grant'), signal, 'POST'),
  withdraw: (sessionId, selectionId, signal) => request(consentUrl(sessionId, selectionId, '/withdraw'), signal, 'POST'),
}
