import type { AssessmentStatus, AssessmentUncertainty } from './assessment'

export interface SupplementalAssessmentState {
  supplementalAssessmentId: string
  baselineAssessmentId: string
  qualityCheckId: string
  submissionId: string
  status: AssessmentStatus
  calculatedAt: string
  inputSnapshotId: string
  modelVersion: string | null
  reasonCode: string | null
  uncertainty: AssessmentUncertainty | null
  acceptedEvidenceCount: number
  demoOnly: true
}

export interface SupplementalAssessmentResponse {
  sessionId: string
  supplementalAssessment: SupplementalAssessmentState | null
}
