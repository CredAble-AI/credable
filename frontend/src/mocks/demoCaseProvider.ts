import type { DemoCaseProvider } from '../api/caseClient'
import { demoCases } from '../data/demoCases'

export const mockDemoCaseProvider: DemoCaseProvider = {
  async create({ demoCaseType }) {
    const option = demoCases.find((item) => item.type === demoCaseType)
    if (!option) throw { code: 'DEMO_CASE_NOT_FOUND', message: '선택한 Demo Case를 찾을 수 없습니다.', retryable: false }
    await new Promise((resolve) => window.setTimeout(resolve, 450))
    const now = new Date().toISOString()
    const caseId = `demo-${demoCaseType.toLowerCase().replace('_', '-')}-${Date.now()}`
    return {
      caseId,
      case: {
        caseId, applicationDate: now, featureCutoffAt: now,
        applicant: { businessName: 'Demo 음식점', industry: '음식업', tenureMonths: option.tenureMonths },
        application: { productType: option.productType }, currentDecision: option.currentDecision,
        declineReasonCodes: option.reasons, demoOnly: true,
      },
    }
  },
}
