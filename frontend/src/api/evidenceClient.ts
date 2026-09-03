import type { ApiError, EvidenceRecommendation, EvidenceRequirementRequest } from '../types/case'

export interface EvidenceProvider {
  getRequirements(request: EvidenceRequirementRequest, signal: AbortSignal): Promise<EvidenceRecommendation>
}

export const normalizeEvidenceError = (error: unknown): ApiError => {
  if (typeof error === 'object' && error !== null && 'code' in error && 'message' in error && 'retryable' in error) return error as ApiError
  return { code: 'EVIDENCE_REQUIREMENTS_FAILED', message: '추천 증빙을 확인하지 못했습니다.', retryable: true }
}

export const liveEvidenceProvider: EvidenceProvider = {
  async getRequirements(body, signal) {
    const response = await fetch('/v1/evidence/requirements', { method: 'POST', signal, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
    if (!response.ok) throw { code: 'EVIDENCE_REQUIREMENTS_FAILED', message: '추천 증빙 요청에 실패했습니다.', requestId: response.headers.get('x-request-id') ?? undefined, retryable: response.status >= 500 } satisfies ApiError
    return response.json() as Promise<EvidenceRecommendation>
  },
}
