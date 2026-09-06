import type { EvidenceSubmissionProvider } from '../api/evidenceSubmissionClient'
import type { EvidenceSubmissionOption } from '../types/evidenceSubmission'

const unavailableOption = (sessionId: string, selectionId: string, evidenceType: string): EvidenceSubmissionOption => ({
  sessionId,
  selectionId,
  evidenceType,
  collectionMode: 'UNAVAILABLE',
  submissionRequirement: {
    status: 'UNAVAILABLE',
    reasonCode: 'DEMO_FILE_BACKEND_REQUIRED',
    consentSourceType: 'CUSTOMER_SUBMITTED',
  },
  demoFile: null,
  uploadPolicy: null,
  demoOnly: true,
})

export const mockEvidenceSubmissionProvider: EvidenceSubmissionProvider = {
  async getOption(sessionId, selectionId, evidenceType, signal) {
    if (signal.aborted) throw new DOMException('Aborted', 'AbortError')
    return unavailableOption(sessionId, selectionId, evidenceType)
  },
  async getLatest(sessionId, signal) {
    if (signal.aborted) throw new DOMException('Aborted', 'AbortError')
    return { sessionId, submission: null }
  },
  async upload() {
    throw { code: 'DEMO_FILE_BACKEND_REQUIRED', message: '파일 제출은 API 연결 Demo 환경에서 확인할 수 있습니다.', retryable: false }
  },
}
