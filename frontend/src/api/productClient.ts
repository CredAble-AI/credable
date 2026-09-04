import type { ApiError } from '../types/case'
import type { ProductCatalogResponse, ProductComparisonResult, ProductConditionQueryResponse, ProductRequest } from '../types/product'

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

const combine = (request: ProductRequest, catalog: ProductCatalogResponse, conditions: ProductConditionQueryResponse): ProductComparisonResult => {
  if (catalog.sessionId !== request.sessionId || conditions.sessionId !== request.sessionId || catalog.catalog.demoOnly !== true || conditions.query.demoOnly !== true) {
    throw { code: 'PRODUCT_RESPONSE_INVALID', message: '현재 세션의 상품 응답을 확인할 수 없습니다.', retryable: false } satisfies ApiError
  }
  const conditionById = new Map(conditions.query.conditions.map((item) => [item.productId, item]))
  const products = catalog.catalog.products.flatMap((product) => {
    const condition = conditionById.get(product.productId)
    return condition ? [{ product, condition, applicationLinkAvailable: product.applicationUrl !== null, applicationUrl: product.applicationUrl }] : []
  })
  return {
    sessionId: request.sessionId, products, catalogStatus: catalog.catalog.status, queryStatus: conditions.query.status,
    availableSortOptions: [{ field: 'ORIGINAL', label: '기본 순서', directions: ['NONE'] }],
    defaultSort: { field: 'ORIGINAL', direction: 'NONE' }, nullPlacement: 'LAST',
    canViewProducts: catalog.catalog.status === 'AVAILABLE',
    cannotProceedReason: catalog.catalog.status === 'AVAILABLE' ? null : (catalog.catalog.reasonCode ?? conditions.query.reasonCode ?? '상품 조건을 조회할 수 없습니다.'),
    resultAt: conditions.query.queriedAt ?? catalog.catalog.retrievedAt, sourceName: null,
    catalogVersion: catalog.catalog.catalogVersion, demoOnly: true,
  }
}

const load = async (request: ProductRequest, signal: AbortSignal, refresh: boolean) => {
  const base = `/v1/sessions/${encodeURIComponent(request.sessionId)}`
  const catalog = await apiRequest<ProductCatalogResponse>(`${base}/products${refresh ? '/refresh' : ''}`, signal, refresh ? 'POST' : 'GET')
  const conditions = await apiRequest<ProductConditionQueryResponse>(`${base}/product-conditions${refresh ? '/query' : ''}`, signal, refresh ? 'POST' : 'GET')
  return combine(request, catalog, conditions)
}

export const liveProductProvider: ProductProvider = {
  get(request, signal) { return load(request, signal, false) },
  refresh(request, signal) { return load(request, signal, true) },
}
