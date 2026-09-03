import type { EvidenceProvider } from '../api/evidenceClient'
import type { ApiError, DemoCaseType, EvidenceRecommendation } from '../types/case'

const score = (evidenceType: string, availability: EvidenceRecommendation['candidates'][number]['availability'], utility: number) => ({ evidenceType, availability, policyRelevance: utility, gapCoverage: utility, crossCheckValue: utility, submissionBurden: 1, privacySensitivity: 1, utility })

const fixtures: Record<Exclude<DemoCaseType, 'HARD_STOP'>, Omit<EvidenceRecommendation, 'recalculatedAt'>> = {
  BORDERLINE: { recommendedEvidenceType: 'RECENT_SALES_DEPOSIT', candidates: [score('RECENT_SALES_DEPOSIT', 'BANK_INTERNAL', 3), score('TAX_FILING', 'CUSTOMER_UPLOAD', 2), score('CARD_POS_SALES', 'PARTNER_REQUIRED', 1)], rationaleCodes: ['RECENT_PERFORMANCE_MISSING', 'SHORT_FINANCIAL_HISTORY'], policyVersion: 'demo-2026.1', basedOn: ['APPLICATION', 'DECLINE_REASON', 'BANK_ACCOUNT'], conditionalSources: ['CARD_POS'], demoOnly: true },
  NO_DATA: { recommendedEvidenceType: 'TAX_FILING', candidates: [score('TAX_FILING', 'CUSTOMER_UPLOAD', 3), score('SIX_MONTH_SALES_DEPOSIT', 'BANK_INTERNAL', 2), score('OTHER_BANK_ACCOUNT', 'CONSENT_REQUIRED', 1)], rationaleCodes: ['EVIDENCE_COVERAGE_GAP'], basedOn: ['APPLICATION', 'DECLINE_REASON', 'CURRENT_EVIDENCE'], conditionalSources: ['OPEN_BANKING'], demoOnly: true },
  SUSPICIOUS: { recommendedEvidenceType: 'SOURCE_VERIFICATION', candidates: [score('SOURCE_VERIFICATION', 'BANK_INTERNAL', 3), score('TAX_CROSS_CHECK', 'CUSTOMER_UPLOAD', 2), score('CARD_POS_LEDGER', 'PARTNER_REQUIRED', 1)], rationaleCodes: ['SOURCE_CONSISTENCY_CHECK', 'DUPLICATE_CHECK'], policyVersion: 'demo-2026.1', basedOn: ['DECLINE_REASON', 'BANK_ACCOUNT', 'CURRENT_EVIDENCE'], conditionalSources: ['CARD_POS'], demoOnly: true },
}

const resolveType = (caseId: string): DemoCaseType | undefined => {
  const values: Array<[string, DemoCaseType]> = [['demo-borderline-', 'BORDERLINE'], ['demo-no-data-', 'NO_DATA'], ['demo-suspicious-', 'SUSPICIOUS'], ['demo-hard-stop-', 'HARD_STOP']]
  return values.find(([prefix]) => caseId.startsWith(prefix))?.[1]
}

const delay = (signal: AbortSignal) => new Promise<void>((resolve, reject) => {
  const timer = window.setTimeout(resolve, 600)
  signal.addEventListener('abort', () => { window.clearTimeout(timer); reject(new DOMException('Aborted', 'AbortError')) }, { once: true })
})

export const mockEvidenceProvider: EvidenceProvider = {
  async getRequirements({ caseId }, signal) {
    await delay(signal)
    const type = resolveType(caseId)
    if (!type || type === 'HARD_STOP') throw { code: 'EVIDENCE_NOT_AVAILABLE', message: '이 Case에는 추천 가능한 증빙이 없습니다.', requestId: 'demo-local', retryable: false } satisfies ApiError
    return { ...fixtures[type], recalculatedAt: new Date().toISOString() }
  },
}
