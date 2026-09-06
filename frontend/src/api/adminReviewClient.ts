import type { ApiError } from '../types/api'
import type { AdminReviewListQuery, AdminReviewQueueResponse } from '../types/adminReview'

export interface AdminReviewProvider {
  list(apiKey: string, query: AdminReviewListQuery, signal: AbortSignal): Promise<AdminReviewQueueResponse>
}

export const normalizeAdminReviewError = (error: unknown): ApiError => {
  if (typeof error === 'object' && error !== null && 'code' in error && 'message' in error && 'retryable' in error) return error as ApiError
  return { code: 'ADMIN_REVIEW_LIST_FAILED', message: '심사역 검토 목록을 확인하지 못했습니다.', retryable: true }
}

const list = async (apiKey: string, query: AdminReviewListQuery, signal: AbortSignal): Promise<AdminReviewQueueResponse> => {
  const params = new URLSearchParams({ limit: String(query.limit), offset: String(query.offset) })
  if (query.status) params.set('status', query.status)
  const response = await fetch(`/v1/admin/underwriter-reviews?${params.toString()}`, {
    method: 'GET',
    headers: { 'X-Admin-API-Key': apiKey },
    signal,
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { error?: ApiError } | null
    throw body?.error ?? { code: 'ADMIN_REVIEW_LIST_FAILED', message: '심사역 검토 목록 요청에 실패했습니다.', requestId: response.headers.get('x-request-id') ?? undefined, retryable: response.status >= 500 } satisfies ApiError
  }
  return response.json() as Promise<AdminReviewQueueResponse>
}

export const liveAdminReviewProvider: AdminReviewProvider = { list }
