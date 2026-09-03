import type { EligibilityProvider } from '../api/eligibilityClient'
import { demoCases } from '../data/demoCases'
import type { ApiError, DemoCaseType, EligibilityResult } from '../types/case'

const eligibilityFixtures: Record<DemoCaseType, Omit<EligibilityResult, 'evaluatedAt'>> = {
  BORDERLINE: { classification: 'SECOND_LOOK_ELIGIBLE', reasons: ['금융이력이 충분하지 않습니다.', '신청 시점에 최근 사업 실적이 반영되지 않았습니다.', '추가 Evidence로 기존 불확실성을 줄일 수 있습니다.'], hardStops: [], demoOnly: true },
  NO_DATA: { classification: 'DATA_QUALITY_ISSUE', reasons: ['판단에 필요한 Evidence의 기간 또는 범위가 부족합니다.', '데이터 부족은 신용위험 악화를 의미하지 않습니다.', '추가 자료를 통해 다시 확인할 수 있습니다.'], hardStops: [], demoOnly: true },
  SUSPICIOUS: { classification: 'DATA_QUALITY_ISSUE', reasons: ['제출된 Evidence에서 출처 또는 정합성 확인이 필요합니다.', '의심 데이터는 위험도 입력에 사용하지 않습니다.', '심사역 확인이 필요할 수 있습니다.'], hardStops: [], demoOnly: true },
  HARD_STOP: { classification: 'HARD_DECLINE', reasons: ['현재 Case에는 정책 또는 컴플라이언스상 Second-Look 제한 사유가 있습니다.'], hardStops: ['정책상 제외 또는 컴플라이언스 필수조건 미충족'], demoOnly: true },
}

const resolveType = (caseId: string): DemoCaseType | undefined => {
  const prefixes: Array<[string, DemoCaseType]> = [['demo-borderline-', 'BORDERLINE'], ['demo-no-data-', 'NO_DATA'], ['demo-suspicious-', 'SUSPICIOUS'], ['demo-hard-stop-', 'HARD_STOP']]
  return prefixes.find(([prefix]) => caseId.startsWith(prefix))?.[1]
}

const delay = (signal: AbortSignal) => new Promise<void>((resolve, reject) => {
  const timer = window.setTimeout(resolve, 650)
  signal.addEventListener('abort', () => { window.clearTimeout(timer); reject(new DOMException('Aborted', 'AbortError')) }, { once: true })
})

const notFound = (): ApiError => ({ code: 'DEMO_CASE_NOT_FOUND', message: '저장된 Demo Case를 찾을 수 없습니다.', requestId: 'demo-local', retryable: false })

export const mockEligibilityProvider: EligibilityProvider = {
  async getCase(caseId, signal) {
    await delay(signal)
    const type = resolveType(caseId)
    const option = demoCases.find((item) => item.type === type)
    if (!option) throw notFound()
    const timestamp = Number(caseId.split('-').at(-1))
    const applicationDate = Number.isFinite(timestamp) ? new Date(timestamp).toISOString() : new Date().toISOString()
    return { caseId, applicationDate, featureCutoffAt: applicationDate, applicant: { businessName: 'Demo 음식점', industry: '음식업', tenureMonths: option.tenureMonths }, application: { productType: option.productType }, currentDecision: option.currentDecision, declineReasonCodes: option.reasons, demoOnly: true }
  },
  async check({ caseId }, signal) {
    await delay(signal)
    const type = resolveType(caseId)
    if (!type) throw notFound()
    return { ...eligibilityFixtures[type], evaluatedAt: new Date().toISOString() }
  },
}
