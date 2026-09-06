export type ExplanationTargetType = 'BASELINE_ASSESSMENT' | 'SUPPLEMENTAL_ASSESSMENT'
export type ExplanationSourceType = 'BASELINE_ASSESSMENT' | 'POLICY_BOUNDARY' | 'SUPPLEMENTAL_ASSESSMENT' | 'ASSESSMENT_COMPARISON' | 'EVIDENCE_RESOLUTION'
export type ExplanationRenderingMode = 'DEMO_TEMPLATE' | 'GENERATIVE_AI' | 'RULE_FALLBACK'

export interface ExplanationSection {
  messageCode: string
  title: string
  text: string
  sourceReferenceIds: string[]
}

export interface ExplanationSourceReference {
  sourceType: ExplanationSourceType
  sourceId: string
  dataVersion: string | null
  modelVersion: string | null
  policyVersion: string | null
}

export interface AssessmentExplanationState {
  explanationId: string
  targetType: ExplanationTargetType
  targetAssessmentId: string
  headline: string
  sections: ExplanationSection[]
  cautionText: string
  sourceReferences: ExplanationSourceReference[]
  inputSnapshotHash: string
  renderingMode: ExplanationRenderingMode
  fallbackApplied: boolean
  fallbackReasonCode: string | null
  providerVersion: string
  modelVersion: string | null
  promptVersion: string
  explanationPolicyVersion: string
  dataVersion: string
  generatedAt: string
  demoOnly: true
}

export interface AssessmentExplanationResponse {
  sessionId: string
  explanation: AssessmentExplanationState | null
}
