import type { AdminEvidenceBurdenResponse } from '../types/adminEvidenceBurden'
import type { ApiError } from '../types/api'

export interface AdminEvidenceBurdenProvider {
  get(sessionId: string, signal: AbortSignal): Promise<AdminEvidenceBurdenResponse>
}

export const normalizeAdminEvidenceBurdenError = (error: unknown): ApiError => {
  if (typeof error === 'object' && error !== null && 'code' in error && 'message' in error && 'retryable' in error) return error as ApiError
  return { code: 'ADMIN_EVIDENCE_BURDEN_REQUEST_FAILED', message: 'Evidence 부담 지표를 확인하지 못했습니다.', retryable: true }
}

const get = async (sessionId: string, signal: AbortSignal): Promise<AdminEvidenceBurdenResponse> => {
  const response = await fetch(`/v1/admin/sessions/${encodeURIComponent(sessionId)}/evidence-burden`, {
    method: 'GET',
    signal,
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { error?: ApiError } | null
    throw body?.error ?? { code: 'ADMIN_EVIDENCE_BURDEN_REQUEST_FAILED', message: 'Evidence 부담 지표 요청에 실패했습니다.', requestId: response.headers.get('x-request-id') ?? undefined, retryable: response.status >= 500 } satisfies ApiError
  }
  return response.json() as Promise<AdminEvidenceBurdenResponse>
}

export const liveAdminEvidenceBurdenProvider: AdminEvidenceBurdenProvider = { get }
