import type { ApiError, EvidenceQualityRequest, EvidenceQualityResponse } from '../types/case'

export interface EvidenceQualityProvider {
  check(request: EvidenceQualityRequest, signal: AbortSignal): Promise<EvidenceQualityResponse>
}

export const normalizeEvidenceQualityError = (error: unknown): ApiError => {
  if (typeof error === 'object' && error !== null && 'code' in error && 'message' in error && 'retryable' in error) return error as ApiError
  return { code: 'EVIDENCE_QUALITY_FAILED', message: 'Evidence 품질을 확인하지 못했습니다.', retryable: true }
}

export const liveEvidenceQualityProvider: EvidenceQualityProvider = {
  async check(body, signal) {
    const response = await fetch('/v1/evidence/quality', { method: 'POST', signal, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
    if (!response.ok) throw { code: 'EVIDENCE_QUALITY_FAILED', message: 'Evidence 품질 확인 요청에 실패했습니다.', requestId: response.headers.get('x-request-id') ?? undefined, retryable: response.status >= 500 } satisfies ApiError
    return response.json() as Promise<EvidenceQualityResponse>
  },
}
