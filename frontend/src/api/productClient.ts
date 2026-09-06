import type { ApiError } from '../types/api'
import type { ProductCatalogResponse, ProductComparisonResponse, ProductComparisonResult, ProductConditionQueryResponse, ProductRequest } from '../types/product'

export interface ProductProvider {
  get(request: ProductRequest, signal: AbortSignal): Promise<ProductComparisonResult>
  refresh(request: ProductRequest, signal: AbortSignal): Promise<ProductComparisonResult>
}

export const normalizeProductError = (error: unknown): ApiError => {
  if (typeof error === 'object' && error !== null && 'code' in error && 'message' in error && 'retryable' in error) return error as ApiError
  return { code: 'PRODUCT_REQUEST_FAILED', message: '상품 조건을 확인하지 못했습니다.', retryable: true }
}

const apiRequest = async <T,>(url: string, signal: AbortSignal, method = 'GET'): Promise<T> => {
  const response = await fetch(url, { method, signal })
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

const refresh = async (request: ProductRequest, signal: AbortSignal): Promise<ProductComparisonResult> => {
  const sessionUrl = `/v1/sessions/${encodeURIComponent(request.sessionId)}`
  const catalog = await apiRequest<ProductCatalogResponse>(`${sessionUrl}/products/refresh`, signal, 'POST')
  if (catalog.sessionId !== request.sessionId || catalog.catalog.demoOnly !== true) throw { code: 'PRODUCT_CATALOG_RESPONSE_INVALID', message: '현재 세션의 상품 카탈로그 응답을 확인할 수 없습니다.', retryable: false } satisfies ApiError
  const conditions = await apiRequest<ProductConditionQueryResponse>(`${sessionUrl}/product-conditions/query`, signal, 'POST')
  if (conditions.sessionId !== request.sessionId || conditions.query.demoOnly !== true) throw { code: 'PRODUCT_CONDITION_RESPONSE_INVALID', message: '현재 세션의 상품 조건 응답을 확인할 수 없습니다.', retryable: false } satisfies ApiError
  return load(request, signal)
}

export const liveProductProvider: ProductProvider = {
  get(request, signal) { return load(request, signal) },
  refresh(request, signal) { return refresh(request, signal) },
}
