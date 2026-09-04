import type { ApiError } from '../types/api'
import type { ConsentSourceType, DataConnectionRequest, DataConnectionResult, DataSourceListResponse, DataSourceState } from '../types/dataConnection'

export interface DataConnectionProvider {
  list(request: DataConnectionRequest, signal: AbortSignal): Promise<DataConnectionResult>
  refresh(request: DataConnectionRequest, signal: AbortSignal): Promise<DataConnectionResult>
  retrySource?(request: DataConnectionRequest, sourceType: ConsentSourceType, signal: AbortSignal): Promise<DataSourceState>
}

export const normalizeDataConnectionError = (error: unknown): ApiError => {
  if (typeof error === 'object' && error !== null && 'code' in error && 'message' in error && 'retryable' in error) return error as ApiError
  return { code: 'DATA_SOURCE_REQUEST_FAILED', message: '데이터 연결 상태를 확인하지 못했습니다.', retryable: true }
}

const request = async (url: string, signal: AbortSignal, method = 'GET'): Promise<DataConnectionResult> => {
  const response = await fetch(url, { method, signal })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { error?: ApiError } | null
    throw body?.error ?? {
      code: 'DATA_SOURCE_REQUEST_FAILED',
      message: '데이터 연결 상태 요청에 실패했습니다.',
      requestId: response.headers.get('x-request-id') ?? undefined,
      retryable: response.status >= 500,
    } satisfies ApiError
  }
  const data = await response.json() as DataSourceListResponse
  return { ...data, canProceed: null, proceedReason: '진행 가능 여부는 Backend 계약 확정 후 제공됩니다.' }
}

export const liveDataConnectionProvider: DataConnectionProvider = {
  list({ sessionId }, signal) {
    return request(`/v1/sessions/${encodeURIComponent(sessionId)}/data-sources`, signal)
  },
  refresh({ sessionId }, signal) {
    return request(`/v1/sessions/${encodeURIComponent(sessionId)}/data-sources/refresh`, signal, 'POST')
  },
}
