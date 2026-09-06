import type { AssessmentComparisonProvider } from '../api/assessmentComparisonClient'
import type { AssessmentComparisonState } from '../types/assessmentComparison'

const results = new Map<string, AssessmentComparisonState>()

export const mockAssessmentComparisonProvider: AssessmentComparisonProvider = {
  async get(sessionId, signal) {
    if (signal.aborted) throw new DOMException('Aborted', 'AbortError')
    return { sessionId, comparison: results.get(sessionId) ?? null }
  },
  async compare(sessionId, context) {
    const comparison: AssessmentComparisonState = {
      comparisonId: `acp_demo_${sessionId}`,
      ...context,
      basis: 'GRADE_SET',
      uncertaintyChange: 'NARROWED',
      beforeUncertainty: { pointEstimate: null, lowerBound: null, upperBound: null, gradeSet: ['DEMO_GRADE_B', 'DEMO_GRADE_C'], calibrationMode: 'RULE_TABLE', calibrationVersion: 'demo-uncertainty-rule-table-v1', demoOnly: true },
      afterUncertainty: { pointEstimate: null, lowerBound: null, upperBound: null, gradeSet: ['DEMO_GRADE_B'], calibrationMode: 'RULE_TABLE', calibrationVersion: 'demo-uncertainty-rule-table-v1', demoOnly: true },
      rationaleCodes: ['GRADE_SET_PROPER_SUBSET'],
      baselineModelVersion: 'demo-small-business-assessment-v1',
      supplementalModelVersion: 'demo-supplemental-assessment-v1',
      comparedAt: new Date().toISOString(),
      demoOnly: true,
    }
    results.set(sessionId, comparison)
    return { sessionId, comparison }
  },
}
