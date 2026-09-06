import type { EvidenceQualityProvider } from '../api/evidenceQualityClient'
import type { EvidenceQualityState } from '../types/evidenceQuality'

const results = new Map<string, EvidenceQualityState>()
const dimensions: EvidenceQualityState['checks'] = [
  ['PROVENANCE', 'DEMO_SOURCE_REFERENCE_PRESENT'], ['FRESHNESS', 'DEMO_FRESHNESS_POLICY_PASSED'],
  ['AUTHENTICITY', 'DEMO_FIXTURE_AUTHENTICITY_PASSED'], ['COMPLETENESS', 'DEMO_REQUIRED_FIELDS_PRESENT'],
  ['CONSISTENCY', 'DEMO_INTERNAL_TOTALS_CONSISTENT'], ['MANIPULATION_RISK', 'DEMO_MANIPULATION_CHECK_PASSED'],
].map(([dimension, rationaleCode]) => ({ dimension, status: 'PASSED', rationaleCode })) as EvidenceQualityState['checks']

export const mockEvidenceQualityProvider: EvidenceQualityProvider = {
  async get(sessionId, submissionId, signal) {
    if (signal.aborted) throw new DOMException('Aborted', 'AbortError')
    return { sessionId, quality: results.get(submissionId) ?? null }
  },
  async check(sessionId, submissionId) {
    const quality: EvidenceQualityState = {
      qualityCheckId: `evq_demo_${submissionId}`, submissionId, evidenceType: 'CUSTOMER_SUBMITTED_RECENT_REVENUE_SUMMARY', status: 'ACCEPTED', checks: dimensions,
      rejectionCodes: [], suspicionCodes: [], eligibleForReassessment: true, nextAction: 'RUN_REASSESSMENT', underwriterRequired: false,
      checkedAt: new Date().toISOString(), submissionSnapshotHash: 'a'.repeat(64), dataVersion: 'demo-evidence-v1', qualityPolicyVersion: 'demo-evidence-quality-policy-v1', demoOnly: true,
    }
    results.set(submissionId, quality)
    return { sessionId, quality }
  },
}
