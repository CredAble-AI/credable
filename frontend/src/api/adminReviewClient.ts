import type { ApiError } from '../types/api'
import type { AdminReviewCompleteRequest, AdminReviewDetailResponse, AdminReviewListQuery, AdminReviewQueueResponse, AdminReviewResultCode } from '../types/adminReview'

export interface AdminReviewProvider {
  list(query: AdminReviewListQuery, signal: AbortSignal): Promise<AdminReviewQueueResponse>
  get(reviewId: string, signal: AbortSignal): Promise<AdminReviewDetailResponse>
  claim(reviewId: string, signal: AbortSignal): Promise<AdminReviewDetailResponse>
  complete(reviewId: string, resultCode: AdminReviewResultCode, decisionNote: string, signal: AbortSignal): Promise<AdminReviewDetailResponse>
}

export const normalizeAdminReviewError = (error: unknown): ApiError => {
  if (typeof error === 'object' && error !== null && 'code' in error && 'message' in error && 'retryable' in error) return error as ApiError
  return { code: 'ADMIN_REVIEW_REQUEST_FAILED', message: '심사역 검토 요청을 처리하지 못했습니다.', retryable: true }
}

const parse = async <T>(response: Response): Promise<T> => {
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { error?: ApiError } | null
    throw body?.error ?? { code: 'ADMIN_REVIEW_REQUEST_FAILED', message: '심사역 검토 요청에 실패했습니다.', requestId: response.headers.get('x-request-id') ?? undefined, retryable: response.status >= 500 } satisfies ApiError
  }
  return response.json() as Promise<T>
}

const list = async (query: AdminReviewListQuery, signal: AbortSignal): Promise<AdminReviewQueueResponse> => {
  const params = new URLSearchParams({ limit: String(query.limit), offset: String(query.offset) })
  if (query.status) params.set('status', query.status)
  const response = await fetch(`/v1/admin/underwriter-reviews?${params.toString()}`, {
    method: 'GET',
    signal,
  })
  return parse<AdminReviewQueueResponse>(response)
}

const reviewPath = (reviewId: string) => `/v1/admin/underwriter-reviews/${encodeURIComponent(reviewId)}`

const get = async (reviewId: string, signal: AbortSignal) => parse<AdminReviewDetailResponse>(await fetch(reviewPath(reviewId), { method: 'GET', signal }))

const claim = async (reviewId: string, signal: AbortSignal) => parse<AdminReviewDetailResponse>(await fetch(`${reviewPath(reviewId)}/claim`, { method: 'POST', signal }))

const complete = async (reviewId: string, resultCode: AdminReviewResultCode, decisionNote: string, signal: AbortSignal) => {
  const body: AdminReviewCompleteRequest = { resultCode, decisionNote }
  return parse<AdminReviewDetailResponse>(await fetch(`${reviewPath(reviewId)}/complete`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  }))
}

export const liveAdminReviewProvider: AdminReviewProvider = { list, get, claim, complete }
