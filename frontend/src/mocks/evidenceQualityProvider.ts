import type { EvidenceQualityProvider } from '../api/evidenceQualityClient'
import type { ApiError, DemoCaseType, EvidenceQualityResponse } from '../types/case'

const fixtures: Record<Exclude<DemoCaseType, 'HARD_STOP'>, Omit<EvidenceQualityResponse, 'evaluatedAt'>> = {
  BORDERLINE: { items: [{ evidenceId: 'demo-sales-deposit', evidenceType: 'RECENT_SALES_DEPOSIT', displayName: '최근 매출 입금 Evidence', status: 'PASS', coveragePct: 100, freshnessDays: 7, sourceVerified: true, consistency: 'OK', anomalyFlags: [], usableForRisk: true, pointInTimeValid: true, sourceType: 'BANK', observedAt: '2026-08-20T09:00:00+09:00', retrievedAt: '2026-09-03T10:00:00+09:00', featureCutoffAt: '2026-09-03T00:00:00+09:00' }], overallGrade: 'GOOD', routeHint: 'SECOND_LOOK', demoOnly: true },
  NO_DATA: { items: [{ evidenceId: 'demo-tax-filing', evidenceType: 'TAX_FILING', displayName: '부가세 신고 Evidence', status: 'FAIL', coveragePct: 42, freshnessDays: 45, sourceVerified: true, consistency: 'CHECK', anomalyFlags: ['INSUFFICIENT_COVERAGE'], usableForRisk: false, pointInTimeValid: true, sourceType: 'MOCK', observedAt: '2026-07-20T09:00:00+09:00', retrievedAt: '2026-09-03T10:00:00+09:00', featureCutoffAt: '2026-09-03T00:00:00+09:00' }], overallGrade: 'INSUFFICIENT', routeHint: 'EVIDENCE_REVIEW', demoOnly: true },
  SUSPICIOUS: { items: [{ evidenceId: 'demo-sales-source', evidenceType: 'SOURCE_VERIFICATION', displayName: '매출 입금 Evidence', status: 'SUSPICIOUS', coveragePct: 88, freshnessDays: 3, sourceVerified: false, consistency: 'FAIL', anomalyFlags: ['SUDDEN_SALES_SPIKE', 'DUPLICATE_TRANSACTION_PATTERN', 'SOURCE_VERIFICATION_REQUIRED'], usableForRisk: false, pointInTimeValid: true, sourceType: 'MOCK', observedAt: '2026-08-30T09:00:00+09:00', retrievedAt: '2026-09-03T10:00:00+09:00', featureCutoffAt: '2026-09-03T00:00:00+09:00' }, { evidenceId: 'demo-after-cutoff', displayName: '심사 이후 추가 매출 자료', status: 'SUSPICIOUS', sourceVerified: true, consistency: 'CHECK', anomalyFlags: [], usableForRisk: false, pointInTimeValid: false, sourceType: 'MOCK', observedAt: '2026-09-04T09:00:00+09:00', featureCutoffAt: '2026-09-03T00:00:00+09:00' }], overallGrade: 'REVIEW_REQUIRED', routeHint: 'UNDERWRITER_REVIEW', demoOnly: true },
}

const resolveType = (caseId: string): DemoCaseType | undefined => {
  const values: Array<[string, DemoCaseType]> = [['demo-borderline-', 'BORDERLINE'], ['demo-no-data-', 'NO_DATA'], ['demo-suspicious-', 'SUSPICIOUS'], ['demo-hard-stop-', 'HARD_STOP']]
  return values.find(([prefix]) => caseId.startsWith(prefix))?.[1]
}

const delay = (signal: AbortSignal) => new Promise<void>((resolve, reject) => {
  const timer = window.setTimeout(resolve, 700)
  signal.addEventListener('abort', () => { window.clearTimeout(timer); reject(new DOMException('Aborted', 'AbortError')) }, { once: true })
})

export const mockEvidenceQualityProvider: EvidenceQualityProvider = {
  async check({ caseId }, signal) {
    await delay(signal)
    const type = resolveType(caseId)
    if (!type || type === 'HARD_STOP') throw { code: 'QUALITY_NOT_AVAILABLE', message: '이 Case의 품질 결과를 확인할 수 없습니다.', requestId: 'demo-local', retryable: false } satisfies ApiError
    return { ...fixtures[type], evaluatedAt: new Date().toISOString() }
  },
}
