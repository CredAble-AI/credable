import type { ApiError, CreateDemoCaseRequest, CreateDemoCaseResponse } from '../types/case'

export interface DemoCaseProvider {
  create(request: CreateDemoCaseRequest): Promise<CreateDemoCaseResponse>
}

export const normalizeApiError = (error: unknown): ApiError => {
  if (typeof error === 'object' && error !== null && 'code' in error && 'message' in error && 'retryable' in error) return error as ApiError
  return { code: 'CASE_CREATE_FAILED', message: 'Case를 생성하지 못했습니다. 잠시 후 다시 시도해주세요.', retryable: true }
}

export const liveDemoCaseProvider: DemoCaseProvider = {
  async create(request) {
    const response = await fetch('/v1/cases/demo', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(request) })
    if (!response.ok) throw { code: 'CASE_CREATE_FAILED', message: 'Case 생성 요청에 실패했습니다.', requestId: response.headers.get('x-request-id') ?? undefined, retryable: response.status >= 500 } satisfies ApiError
    return response.json() as Promise<CreateDemoCaseResponse>
  },
}
