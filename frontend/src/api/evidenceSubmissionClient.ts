import type { ApiError } from '../types/api'
import type { EvidenceSubmissionOption, EvidenceSubmissionResponse } from '../types/evidenceSubmission'

export interface EvidenceSubmissionProvider {
  getOption(sessionId: string, selectionId: string, evidenceType: string, signal: AbortSignal): Promise<EvidenceSubmissionOption>
  getLatest(sessionId: string, signal: AbortSignal): Promise<EvidenceSubmissionResponse>
  upload(sessionId: string, selectionId: string, file: File, signal: AbortSignal): Promise<EvidenceSubmissionResponse>
  submitConnected(sessionId: string, selectionId: string, signal: AbortSignal): Promise<EvidenceSubmissionResponse>
}

export const normalizeEvidenceSubmissionError = (error: unknown): ApiError => {
  if (typeof error === 'object' && error !== null && 'code' in error && 'message' in error && 'retryable' in error) return error as ApiError
  return { code: 'EVIDENCE_SUBMISSION_REQUEST_FAILED', message: 'Evidence 제출 상태를 확인하지 못했습니다.', retryable: true }
}

const request = async <T,>(url: string, signal: AbortSignal, init: RequestInit = {}): Promise<T> => {
  const response = await fetch(url, { ...init, signal })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { error?: ApiError } | null
    throw body?.error ?? {
      code: 'EVIDENCE_SUBMISSION_REQUEST_FAILED',
      message: 'Evidence 제출 요청에 실패했습니다.',
      requestId: response.headers.get('x-request-id') ?? undefined,
      retryable: response.status >= 500,
    } satisfies ApiError
  }
  return response.json() as Promise<T>
}

const evidenceUrl = (sessionId: string, suffix: string) => `/v1/sessions/${encodeURIComponent(sessionId)}/evidence${suffix}`

export const liveEvidenceSubmissionProvider: EvidenceSubmissionProvider = {
  getOption(sessionId, selectionId, _evidenceType, signal) {
    return request(evidenceUrl(sessionId, `/selections/${encodeURIComponent(selectionId)}/submission-option`), signal)
  },
  getLatest(sessionId, signal) {
    return request(evidenceUrl(sessionId, '/submissions/latest'), signal)
  },
  upload(sessionId, selectionId, file, signal) {
    const body = new FormData()
    body.append('selectionId', selectionId)
    body.append('file', file)
    return request(evidenceUrl(sessionId, '/submissions/upload'), signal, { method: 'POST', body })
  },
  submitConnected(sessionId, selectionId, signal) {
    return request(evidenceUrl(sessionId, '/submissions'), signal, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ selectionId, submissionMode: 'DEMO_FIXTURE_REFERENCE' }),
    })
  },
}
