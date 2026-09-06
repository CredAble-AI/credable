import type { EvidenceResolutionProvider } from '../api/evidenceResolutionClient'
import type { EvidenceResolutionState } from '../types/evidenceResolution'

const results = new Map<string, EvidenceResolutionState>()

export const mockEvidenceResolutionProvider: EvidenceResolutionProvider = {
  async get(sessionId, signal) {
    if (signal.aborted) throw new DOMException('Aborted', 'AbortError')
    return { sessionId, resolution: results.get(sessionId) ?? null }
  },
  async resolve(sessionId, context) {
    const resolution: EvidenceResolutionState = {
      resolutionId: `res_demo_${sessionId}`,
      ...context,
      status: 'RESOLVED',
      nextAction: 'SHOW_UPDATED_RESULTS',
      stopEvidenceCollection: true,
      underwriterRequired: false,
      reasonCode: 'PATH_STABLE',
      possibleRoutes: ['DEMO_PATH_1'],
      crossedBoundaryCodes: [],
      resolvedAt: new Date().toISOString(),
      calibrationVersion: 'demo-uncertainty-rule-table-v1',
      boundaryPolicyVersion: 'demo-policy-boundary-v1',
      demoOnly: true,
    }
    results.set(sessionId, resolution)
    return { sessionId, resolution }
  },
}
