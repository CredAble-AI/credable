import type { ConsentProvider } from '../api/consentClient'
import type { ApiError } from '../types/api'
import type { ConsentListResponse, ConsentSourceType, ConsentState, ConsentStatus } from '../types/consent'
import type { ConsentSelections, CustomerSession } from '../types/customerSession'
import { mockCustomerSessionProvider } from './customerSessionProvider'

const SCOPE_VERSION = 'demo-consent-scopes-v2'
const definitions = [
  ['BANK_INTERNAL', '은행 내부 데이터', '도입 은행이 보유한 고객·계좌·대출 관련 데이터', true],
  ['CREDIT_INFORMATION', '신용정보', '은행이 정식 절차로 조회하는 신용정보', true],
  ['CUSTOMER_SUBMITTED', '고객 제출 데이터', '고객이 직접 제출하는 소득·사업·재무 관련 데이터', false],
  ['EXTERNAL_CONNECTED', '외부 연결 데이터', '고객 동의와 제휴 범위 안에서 연결하는 외부 데이터', false],
] as const

const wait = (signal: AbortSignal, milliseconds = 180) => new Promise<void>((resolve, reject) => {
  const timer = window.setTimeout(resolve, milliseconds)
  signal.addEventListener('abort', () => { window.clearTimeout(timer); reject(new DOMException('Aborted', 'AbortError')) }, { once: true })
})

const isGranted = (session: CustomerSession, sourceType: ConsentSourceType) => {
  if (sourceType === 'BANK_INTERNAL') return session.consents.required.customerIdentity && session.consents.required.accountSummary
  if (sourceType === 'CREDIT_INFORMATION') return session.consents.required.creditInformation
  if (sourceType === 'CUSTOMER_SUBMITTED') return session.consents.optional.submittedDocuments
  return session.consents.optional.otherInstitutions && session.consents.optional.partnerData
}

const updateSelections = (current: ConsentSelections, sourceType: ConsentSourceType, granted: boolean): ConsentSelections => {
  if (sourceType === 'BANK_INTERNAL') return { ...current, required: { ...current.required, customerIdentity: granted, accountSummary: granted } }
  if (sourceType === 'CREDIT_INFORMATION') return { ...current, required: { ...current.required, creditInformation: granted } }
  if (sourceType === 'CUSTOMER_SUBMITTED') return { ...current, optional: { ...current.optional, submittedDocuments: granted } }
  return { ...current, optional: { ...current.optional, otherInstitutions: granted, partnerData: granted } }
}

const state = (sourceType: ConsentSourceType, status: ConsentStatus, timestamp: string | null = null): ConsentState => {
  const definition = definitions.find(([type]) => type === sourceType)
  if (!definition) throw { code: 'CONSENT_SCOPE_NOT_FOUND', message: '동의 범위를 찾을 수 없습니다.', retryable: false } satisfies ApiError
  const [, displayName, description, required] = definition
  return {
    sourceType,
    displayName,
    description,
    required,
    status,
    grantedAt: status === 'GRANTED' || status === 'WITHDRAWN' ? timestamp : null,
    withdrawnAt: status === 'WITHDRAWN' ? timestamp : null,
    updatedAt: status === 'PENDING' ? null : timestamp,
    scopeVersion: SCOPE_VERSION,
    demoOnly: true,
  }
}

const getSession = async (sessionId: string, signal: AbortSignal) => {
  const session = await mockCustomerSessionProvider.get(signal)
  if (!session || session.sessionId !== sessionId) throw { code: 'CUSTOMER_SESSION_NOT_FOUND', message: '고객 세션을 찾을 수 없습니다.', retryable: false } satisfies ApiError
  return session
}

const changeConsent = async (sessionId: string, sourceType: ConsentSourceType, granted: boolean, signal: AbortSignal) => {
  await wait(signal)
  const session = await getSession(sessionId, signal)
  const updated = await mockCustomerSessionProvider.updateConsents(updateSelections(session.consents, sourceType, granted), signal)
  if (!updated) throw { code: 'CUSTOMER_SESSION_NOT_FOUND', message: '고객 세션을 찾을 수 없습니다.', retryable: false } satisfies ApiError
  const now = new Date().toISOString()
  return state(sourceType, granted ? 'GRANTED' : 'WITHDRAWN', now)
}

export const mockConsentProvider: ConsentProvider = {
  async list(sessionId, signal) {
    await wait(signal)
    const session = await getSession(sessionId, signal)
    return {
      sessionId,
      consents: definitions.map(([sourceType]) => state(sourceType, isGranted(session, sourceType) ? 'GRANTED' : 'PENDING', isGranted(session, sourceType) ? new Date().toISOString() : null)),
      scopeVersion: SCOPE_VERSION,
      demoOnly: true,
    } satisfies ConsentListResponse
  },
  grant(sessionId, sourceType, signal) {
    return changeConsent(sessionId, sourceType, true, signal)
  },
  withdraw(sessionId, sourceType, signal) {
    return changeConsent(sessionId, sourceType, false, signal)
  },
}
