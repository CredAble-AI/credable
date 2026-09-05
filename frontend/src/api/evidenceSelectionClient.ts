import type { ApiError } from '../types/api'
import type { EvidenceSelectionResponse } from '../types/evidenceSelection'

export interface EvidenceSelectionProvider {
  get(sessionId: string, signal: AbortSignal): Promise<EvidenceSelectionResponse>
  selectNext(sessionId: string, signal: AbortSignal): Promise<EvidenceSelectionResponse>
}

export const normalizeEvidenceSelectionError = (error: unknown): ApiError => {
  if (typeof error === 'object' && error !== null && 'code' in error && 'message' in error && 'retryable' in error) return error as ApiError
  return { code: 'EVIDENCE_SELECTION_REQUEST_FAILED', message: 'Evidence 선택 상태를 확인하지 못했습니다.', retryable: true }
}

const requestSelection = async (url: string, signal: AbortSignal, method = 'GET'): Promise<EvidenceSelectionResponse> => {
  const response = await fetch(url, { method, signal })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { error?: ApiError } | null
    throw body?.error ?? {
      code: 'EVIDENCE_SELECTION_REQUEST_FAILED',
      message: 'Evidence 선택 요청에 실패했습니다.',
      requestId: response.headers.get('x-request-id') ?? undefined,
      retryable: response.status >= 500,
    } satisfies ApiError
  }
  return response.json() as Promise<EvidenceSelectionResponse>
}

const selectionUrl = (sessionId: string) => `/v1/sessions/${encodeURIComponent(sessionId)}/evidence/next`

export const liveEvidenceSelectionProvider: EvidenceSelectionProvider = {
  get(sessionId, signal) { return requestSelection(selectionUrl(sessionId), signal) },
  selectNext(sessionId, signal) { return requestSelection(selectionUrl(sessionId), signal, 'POST') },
}
