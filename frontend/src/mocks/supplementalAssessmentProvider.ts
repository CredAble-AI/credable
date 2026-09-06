import type { SupplementalAssessmentProvider } from '../api/supplementalAssessmentClient'
import type { SupplementalAssessmentState } from '../types/supplementalAssessment'

const results = new Map<string, SupplementalAssessmentState>()
export const getMockSupplementalAssessmentResult = (sessionId: string) => results.get(sessionId) ?? null

export const mockSupplementalAssessmentProvider: SupplementalAssessmentProvider = {
  async get(sessionId, signal) {
    if (signal.aborted) throw new DOMException('Aborted', 'AbortError')
    return { sessionId, supplementalAssessment: results.get(sessionId) ?? null }
  },
  async run(sessionId, submissionId) {
    const supplementalAssessment: SupplementalAssessmentState = {
      supplementalAssessmentId: `sam_demo_${sessionId}_${submissionId}`, baselineAssessmentId: `asm_demo_${sessionId}`, qualityCheckId: `evq_demo_${submissionId}`, submissionId,
      status: 'COMPLETED', calculatedAt: new Date().toISOString(), inputSnapshotId: `sas_demo_${submissionId}`, modelVersion: 'demo-supplemental-assessment-v1', reasonCode: null,
      uncertainty: { pointEstimate: null, lowerBound: null, upperBound: null, gradeSet: ['DEMO_GRADE_B'], calibrationMode: 'RULE_TABLE', calibrationVersion: 'demo-uncertainty-rule-table-v1', demoOnly: true },
      acceptedEvidenceCount: 1, demoOnly: true,
    }
    results.set(sessionId, supplementalAssessment)
    return { sessionId, supplementalAssessment }
  },
}
