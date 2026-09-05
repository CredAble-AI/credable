import type { DemoProfileType } from './customerSession'

export type AssessmentStatus = 'NOT_RUN' | 'MODEL_NOT_CONFIGURED' | 'COMPLETED' | 'INSUFFICIENT_DATA' | 'UNSUPPORTED_CUSTOMER_TYPE' | 'FAILED'
export type CalibrationMode = 'RULE_TABLE' | 'CONFORMAL_CALIBRATED'

export interface AssessmentUncertainty {
  pointEstimate: number | null
  lowerBound: number | null
  upperBound: number | null
  gradeSet: string[]
  calibrationMode: CalibrationMode
  calibrationVersion: string
  demoOnly: true
}

export interface AssessmentState {
  assessmentId: string | null
  status: AssessmentStatus
  calculatedAt: string | null
  inputSnapshotId: string | null
  modelVersion: string | null
  reasonCode: string | null
  uncertainty: AssessmentUncertainty | null
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
