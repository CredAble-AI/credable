import type { ApiError } from '../types/api'
import type { ConsentSourceType, DataSourceListResponse, DataSourceState } from '../types/dataConnection'

export interface DataConnectionProvider {
  list(sessionId: string, signal: AbortSignal): Promise<DataSourceListResponse>
  refresh(sessionId: string, signal: AbortSignal): Promise<DataSourceListResponse>
  retrySource?(sessionId: string, sourceType: ConsentSourceType, signal: AbortSignal): Promise<DataSourceState>
}

export const normalizeDataConnectionError = (error: unknown): ApiError => {
  if (typeof error === 'object' && error !== null && 'code' in error && 'message' in error && 'retryable' in error) return error as ApiError
  return { code: 'DATA_SOURCE_REQUEST_FAILED', message: '데이터 연결 상태를 확인하지 못했습니다.', retryable: true }
}

const request = async (url: string, signal: AbortSignal, method = 'GET'): Promise<DataSourceListResponse> => {
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
  return response.json() as Promise<DataSourceListResponse>
}

export const liveDataConnectionProvider: DataConnectionProvider = {
  list(sessionId, signal) {
    return request(`/v1/sessions/${encodeURIComponent(sessionId)}/data-sources`, signal)
  },
  refresh(sessionId, signal) {
    return request(`/v1/sessions/${encodeURIComponent(sessionId)}/data-sources/refresh`, signal, 'POST')
  },
}
