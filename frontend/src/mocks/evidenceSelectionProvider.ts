import type { EvidenceSelectionProvider } from '../api/evidenceSelectionClient'
import type { EvidenceSelectionResponse } from '../types/evidenceSelection'

const selections = new Map<string, EvidenceSelectionResponse>()
const wait = (signal: AbortSignal, milliseconds: number) => new Promise<void>((resolve, reject) => {
  const timer = window.setTimeout(resolve, milliseconds)
  signal.addEventListener('abort', () => { window.clearTimeout(timer); reject(new DOMException('Aborted', 'AbortError')) }, { once: true })
})

export const mockEvidenceSelectionProvider: EvidenceSelectionProvider = {
  async get(sessionId, signal) {
    await wait(signal, 350)
    return selections.get(sessionId) ?? { sessionId, selection: null }
  },
  async selectNext(sessionId, signal) {
    await wait(signal, 650)
    const response: EvidenceSelectionResponse = {
      sessionId,
      selection: {
        selectionId: `evs_demo_${sessionId}`,
        boundaryCheckId: `pbc_demo_${sessionId}`,
        resolutionId: null,
        rejectedQualityCheckId: null,
        iteration: 1,
        maxEvidenceRequests: 2,
        status: 'SELECTED',
        selectedEvidence: {
          evidenceType: 'CUSTOMER_SUBMITTED_RECENT_REVENUE_SUMMARY',
          displayName: '최근 매출·입금 요약',
          description: '최근 매출 발생과 실제 입금 흐름을 확인할 수 있는 고객 제출 자료',
          sourceType: 'CUSTOMER_SUBMITTED',
          collectionMode: 'UNAVAILABLE',
          availability: 'CONSENT_REQUIRED',
          rationaleCodes: ['DEMO_RESOLVE_BOUNDARY_1_2', 'DEMO_MINIMUM_SINGLE_REQUEST'],
          consentScope: { scopeVersion: 'demo-recent-revenue-consent-v1', purposeCode: 'SUPPLEMENTAL_CREDIT_ASSESSMENT', purposeDescription: '기존 평가의 불확실성을 확인하기 위한 보완평가에 사용', dataCategories: ['BUSINESS_IDENTITY', 'MONTHLY_SALES', 'MONTHLY_DEPOSITS', 'PERIOD_TOTALS'], periodStart: '2026-03-01', periodEnd: '2026-08-31', required: true },
          demoOnly: true,
        },
        evaluatedCandidateCount: 2,
        stopReason: null,
        underwriterRequired: false,
        selectedAt: '2026-09-04T11:02:00+09:00',
        calibrationVersion: 'demo-uncertainty-rule-table-v1',
        boundaryPolicyVersion: 'demo-policy-boundary-v1',
        selectionPolicyVersion: 'demo-active-evidence-selection-v1',
        demoOnly: true,
      },
    }
    selections.set(sessionId, response)
    return response
  },
}
