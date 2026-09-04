import type { ApiError } from '../types/api'
import type { ProductComparisonResponse, ProductComparisonResult, ProductRequest } from '../types/product'

export interface ProductProvider {
  get(request: ProductRequest, signal: AbortSignal): Promise<ProductComparisonResult>
  refresh(request: ProductRequest, signal: AbortSignal): Promise<ProductComparisonResult>
}

export const normalizeProductError = (error: unknown): ApiError => {
  if (typeof error === 'object' && error !== null && 'code' in error && 'message' in error && 'retryable' in error) return error as ApiError
  return { code: 'PRODUCT_REQUEST_FAILED', message: '상품 조건을 확인하지 못했습니다.', retryable: true }
}

const apiRequest = async <T,>(url: string, signal: AbortSignal): Promise<T> => {
  const response = await fetch(url, { method: 'GET', signal })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { error?: ApiError } | null
    throw body?.error ?? { code: 'PRODUCT_REQUEST_FAILED', message: '상품 조건 요청에 실패했습니다.', requestId: response.headers.get('x-request-id') ?? undefined, retryable: response.status >= 500 } satisfies ApiError
  }
  return response.json() as Promise<T>
}

const toResult = (request: ProductRequest, response: ProductComparisonResponse): ProductComparisonResult => {
  if (response.sessionId !== request.sessionId || response.demoOnly !== true) {
    throw { code: 'PRODUCT_RESPONSE_INVALID', message: '현재 세션의 상품 응답을 확인할 수 없습니다.', retryable: false } satisfies ApiError
  }
  return {
    sessionId: response.sessionId,
    products: response.items.map((item) => ({
      product: item,
      applicationLinkAvailable: item.applicationUrl !== null,
      applicationUrl: item.applicationUrl,
    })),
    status: response.status,
    sortableFields: response.sortableFields,
    nullPlacement: response.nullPlacement,
    initialOrder: response.initialOrder,
    canViewProducts: response.status !== 'CATALOG_UNAVAILABLE',
    cannotProceedReason: response.status === 'CATALOG_UNAVAILABLE' ? (response.reasonCode ?? '상품 조건을 조회할 수 없습니다.') : null,
    resultAt: response.assembledAt,
    catalogSnapshotId: response.catalogSnapshotId,
    demoOnly: true,
  }
}

const load = async (request: ProductRequest, signal: AbortSignal): Promise<ProductComparisonResult> => {
  const url = `/v1/sessions/${encodeURIComponent(request.sessionId)}/comparison`
  const response = await apiRequest<ProductComparisonResponse>(url, signal)
  return toResult(request, response)
}

export const liveProductProvider: ProductProvider = {
  get(request, signal) { return load(request, signal) },
  // GET /v1/sessions/{sessionId}/comparison has no dedicated refresh action; refresh re-issues the same GET.
  refresh(request, signal) { return load(request, signal) },
}
