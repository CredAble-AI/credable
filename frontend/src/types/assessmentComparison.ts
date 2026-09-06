import type { AssessmentUncertainty } from './assessment'

export type AssessmentComparisonBasis = 'GRADE_SET' | 'NUMERIC_INTERVAL' | 'NOT_COMPARABLE'
export type AssessmentUncertaintyChange = 'NARROWED' | 'UNCHANGED' | 'EXPANDED' | 'SHIFTED' | 'NOT_COMPARABLE'

export interface AssessmentComparisonState {
  comparisonId: string
  baselineAssessmentId: string
  supplementalAssessmentId: string
  qualityCheckId: string
  basis: AssessmentComparisonBasis
  uncertaintyChange: AssessmentUncertaintyChange
  beforeUncertainty: AssessmentUncertainty | null
  afterUncertainty: AssessmentUncertainty | null
  rationaleCodes: string[]
  baselineModelVersion: string | null
  supplementalModelVersion: string | null
  comparedAt: string
  demoOnly: true
}

export interface AssessmentComparisonResponse {
  sessionId: string
  comparison: AssessmentComparisonState | null
}

export interface AssessmentComparisonContext {
  baselineAssessmentId: string
  supplementalAssessmentId: string
  qualityCheckId: string
}
