import type { DemoProfileType } from './customerSession'

// Mirrors the current backend assessment response. Presentation fields live in AssessmentResult.
export type AssessmentStatus = 'NOT_RUN' | 'MODEL_NOT_CONFIGURED' | 'COMPLETED' | 'INSUFFICIENT_DATA' | 'UNSUPPORTED_CUSTOMER_TYPE' | 'FAILED'

export interface AssessmentState {
  assessmentId?: string | null
  status: AssessmentStatus
  calculatedAt?: string | null
  inputSnapshotId?: string | null
  modelVersion?: string | null
  reasonCode?: string | null
  demoOnly: true
}

export interface AssessmentResponse {
  sessionId: string
  assessment: AssessmentState
}

export interface AssessmentRequest {
  sessionId: string
  profileType: DemoProfileType
}

export interface AssessmentResult extends AssessmentResponse {
  summary?: string
  dataSummary: string[]
  excludedData: string[]
  canProceed: boolean | null
  proceedReason?: string
  resultMode: 'LIVE' | 'MOCK'
}
