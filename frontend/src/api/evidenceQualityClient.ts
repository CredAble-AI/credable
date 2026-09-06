import type { ApiError } from '../types/api'
import type { EvidenceQualityResponse } from '../types/evidenceQuality'

export interface EvidenceQualityProvider {
  get(sessionId: string, submissionId: string, signal: AbortSignal): Promise<EvidenceQualityResponse>
  check(sessionId: string, submissionId: string, signal: AbortSignal): Promise<EvidenceQualityResponse>
}

export const normalizeEvidenceQualityError = (error: unknown): ApiError => {
  if (typeof error === 'object' && error !== null && 'code' in error && 'message' in error && 'retryable' in error) return error as ApiError
  return { code: 'EVIDENCE_QUALITY_REQUEST_FAILED', message: 'Evidence 품질검증 상태를 확인하지 못했습니다.', retryable: true }
}

const request = async (url: string, signal: AbortSignal, method = 'GET'): Promise<EvidenceQualityResponse> => {
  const response = await fetch(url, { method, signal })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { error?: ApiError } | null
    throw body?.error ?? { code: 'EVIDENCE_QUALITY_REQUEST_FAILED', message: 'Evidence 품질검증 요청에 실패했습니다.', requestId: response.headers.get('x-request-id') ?? undefined, retryable: response.status >= 500 } satisfies ApiError
  }
  return response.json() as Promise<EvidenceQualityResponse>
}

const qualityUrl = (sessionId: string, submissionId: string) => `/v1/sessions/${encodeURIComponent(sessionId)}/evidence/submissions/${encodeURIComponent(submissionId)}/quality`

export const liveEvidenceQualityProvider: EvidenceQualityProvider = {
  get: (sessionId, submissionId, signal) => request(qualityUrl(sessionId, submissionId), signal),
  check: (sessionId, submissionId, signal) => request(qualityUrl(sessionId, submissionId), signal, 'POST'),
}
