import type { ApiError } from '../types/api'
import type { EvidenceResolutionContext, EvidenceResolutionResponse } from '../types/evidenceResolution'

export interface EvidenceResolutionProvider {
  get(sessionId: string, signal: AbortSignal): Promise<EvidenceResolutionResponse>
  resolve(sessionId: string, context: EvidenceResolutionContext, signal: AbortSignal): Promise<EvidenceResolutionResponse>
}

export const normalizeEvidenceResolutionError = (error: unknown): ApiError => {
  if (typeof error === 'object' && error !== null && 'code' in error && 'message' in error && 'retryable' in error) return error as ApiError
  return { code: 'EVIDENCE_RESOLUTION_REQUEST_FAILED', message: 'Evidence 수집 판단을 확인하지 못했습니다.', retryable: true }
}

const request = async (sessionId: string, signal: AbortSignal, method = 'GET'): Promise<EvidenceResolutionResponse> => {
  const response = await fetch(`/v1/sessions/${encodeURIComponent(sessionId)}/assessment/resolution`, { method, signal })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { error?: ApiError } | null
    throw body?.error ?? { code: 'EVIDENCE_RESOLUTION_REQUEST_FAILED', message: 'Evidence 수집 판단 요청에 실패했습니다.', requestId: response.headers.get('x-request-id') ?? undefined, retryable: response.status >= 500 } satisfies ApiError
  }
  return response.json() as Promise<EvidenceResolutionResponse>
}

export const liveEvidenceResolutionProvider: EvidenceResolutionProvider = {
  get: (sessionId, signal) => request(sessionId, signal),
  resolve: (sessionId, _context, signal) => request(sessionId, signal, 'POST'),
}
