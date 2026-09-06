import type { EvidenceConsentProvider } from '../api/evidenceConsentClient'
import type { EvidenceConsentResponse, EvidenceConsentState } from '../types/evidenceConsent'

const states = new Map<string, EvidenceConsentState>()
const key = (sessionId: string, selectionId: string) => `${sessionId}:${selectionId}`
const initialState = (selectionId: string): EvidenceConsentState => ({
  evidenceConsentId: `evc_demo_${selectionId}`, selectionId, evidenceType: 'CUSTOMER_SUBMITTED_RECENT_REVENUE_SUMMARY', sourceType: 'CUSTOMER_SUBMITTED',
  purposeCode: 'SUPPLEMENTAL_CREDIT_ASSESSMENT', purposeDescription: '기존 평가의 불확실성을 확인하기 위한 보완평가에 사용',
  dataCategories: ['BUSINESS_IDENTITY', 'MONTHLY_SALES', 'MONTHLY_DEPOSITS', 'PERIOD_TOTALS'], periodStart: '2026-03-01', periodEnd: '2026-08-31', required: true,
  status: 'PENDING', grantedAt: null, withdrawnAt: null, updatedAt: null, scopeVersion: 'demo-recent-revenue-consent-v1', demoOnly: true,
})

const response = (sessionId: string, selectionId: string, consent: EvidenceConsentState): EvidenceConsentResponse => ({ sessionId, selectionId, consent })

export const mockEvidenceConsentProvider: EvidenceConsentProvider = {
  async get(sessionId, selectionId, signal) {
    if (signal.aborted) throw new DOMException('Aborted', 'AbortError')
    const consent = states.get(key(sessionId, selectionId)) ?? initialState(selectionId)
    return response(sessionId, selectionId, consent)
  },
  async grant(sessionId, selectionId) {
    const current = states.get(key(sessionId, selectionId)) ?? initialState(selectionId)
    const timestamp = new Date().toISOString()
    const updated = { ...current, status: 'GRANTED' as const, grantedAt: timestamp, withdrawnAt: null, updatedAt: timestamp }
    states.set(key(sessionId, selectionId), updated)
    return response(sessionId, selectionId, updated)
  },
  async withdraw(sessionId, selectionId) {
    const current = states.get(key(sessionId, selectionId)) ?? initialState(selectionId)
    if (current.status !== 'GRANTED') throw { code: 'EVIDENCE_CONSENT_NOT_GRANTED', message: '승인되지 않은 Evidence 동의는 철회할 수 없습니다.', retryable: false }
    const timestamp = new Date().toISOString()
    const updated = { ...current, status: 'WITHDRAWN' as const, withdrawnAt: timestamp, updatedAt: timestamp }
    states.set(key(sessionId, selectionId), updated)
    return response(sessionId, selectionId, updated)
  },
}
