import type { ApiError } from '../types/api'
import type { AdminAuditEventListResponse } from '../types/adminAudit'

export interface AdminAuditProvider {
  list(sessionId: string, limit: number, cursor: string | null, signal: AbortSignal): Promise<AdminAuditEventListResponse>
}

export const normalizeAdminAuditError = (error: unknown): ApiError => {
  if (typeof error === 'object' && error !== null && 'code' in error && 'message' in error && 'retryable' in error) return error as ApiError
  return { code: 'ADMIN_AUDIT_REQUEST_FAILED', message: '세션 감사 이력을 확인하지 못했습니다.', retryable: true }
}

const list = async (sessionId: string, limit: number, cursor: string | null, signal: AbortSignal): Promise<AdminAuditEventListResponse> => {
  const params = new URLSearchParams({ limit: String(limit) })
  if (cursor) params.set('cursor', cursor)
  const response = await fetch(`/v1/admin/sessions/${encodeURIComponent(sessionId)}/audit-events?${params.toString()}`, {
    method: 'GET',
    signal,
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { error?: ApiError } | null
    throw body?.error ?? { code: 'ADMIN_AUDIT_REQUEST_FAILED', message: '세션 감사 이력 요청에 실패했습니다.', requestId: response.headers.get('x-request-id') ?? undefined, retryable: response.status >= 500 } satisfies ApiError
  }
  return response.json() as Promise<AdminAuditEventListResponse>
}

export const liveAdminAuditProvider: AdminAuditProvider = { list }
