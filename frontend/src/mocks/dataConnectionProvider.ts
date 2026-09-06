import type { DataConnectionProvider } from '../api/dataConnectionClient'
import type { ApiError } from '../types/api'
import type { ConsentSourceType, DataSourceListResponse, DataSourceState } from '../types/dataConnection'
import type { CustomerSession } from '../types/customerSession'
import { mockCustomerSessionProvider } from './customerSessionProvider'

const definitions = [
  ['BANK_INTERNAL', '은행 내부 데이터'],
  ['CREDIT_INFORMATION', '신용정보'],
  ['CUSTOMER_SUBMITTED', '고객 제출 데이터'],
  ['EXTERNAL_CONNECTED', '외부 연결 데이터'],
] as const

const wait = (signal: AbortSignal, milliseconds = 650) => new Promise<void>((resolve, reject) => {
  const timer = window.setTimeout(resolve, milliseconds)
  signal.addEventListener('abort', () => { window.clearTimeout(timer); reject(new DOMException('Aborted', 'AbortError')) }, { once: true })
})

const isGranted = (session: CustomerSession, sourceType: ConsentSourceType) => {
  if (sourceType === 'BANK_INTERNAL') return session.consents.required.customerIdentity && session.consents.required.accountSummary
  if (sourceType === 'CREDIT_INFORMATION') return session.consents.required.creditInformation
  if (sourceType === 'CUSTOMER_SUBMITTED') return session.consents.optional.submittedDocuments
  return session.consents.optional.otherInstitutions && session.consents.optional.partnerData
}

const state = (sourceType: ConsentSourceType, displayName: string, overrides: Partial<DataSourceState> = {}): DataSourceState => ({
  sourceType,
  displayName,
  retrievalStatus: 'NOT_REQUESTED',
  verificationStatus: 'NOT_STARTED',
  observedAt: null,
  retrievedAt: null,
  dataVersion: null,
  reasonCode: null,
  demoOnly: true,
  ...overrides,
})

const consentRequired = (sourceType: ConsentSourceType, displayName: string) => state(sourceType, displayName, {
  retrievalStatus: 'CONSENT_REQUIRED',
  reasonCode: 'CONSENT_REQUIRED',
})

const refreshed = (session: CustomerSession, sourceType: ConsentSourceType, displayName: string): DataSourceState => {
  const corporation = session.demoProfile.businessBorrowerType === 'CORPORATION'
  return state(sourceType, displayName, {
    retrievalStatus: 'RETRIEVED',
    verificationStatus: corporation && sourceType === 'CUSTOMER_SUBMITTED' ? 'STALE' : 'VERIFIED',
    observedAt: corporation && sourceType === 'CUSTOMER_SUBMITTED' ? '2025-12-31T23:59:59+09:00' : '2026-08-31T23:59:59+09:00',
    retrievedAt: new Date().toISOString(),
    dataVersion: sourceType === 'BANK_INTERNAL'
      ? 'synthetic-bank-data-v1'
      : sourceType === 'CREDIT_INFORMATION'
        ? 'synthetic-credit-information-v1'
        : 'synthetic-demo-v1',
    reasonCode: corporation && sourceType === 'CUSTOMER_SUBMITTED' ? 'DEMO_OBSERVATION_STALE' : null,
  })
}

const getSession = async (sessionId: string, signal: AbortSignal) => {
  const session = await mockCustomerSessionProvider.get(signal)
  if (!session || session.sessionId !== sessionId) throw {
    code: 'CUSTOMER_SESSION_NOT_FOUND',
    message: '고객 세션을 찾을 수 없습니다.',
    retryable: false,
  } satisfies ApiError
  return session
}

const response = (session: CustomerSession, refresh: boolean): DataSourceListResponse => ({
  sessionId: session.sessionId,
  dataSources: definitions.map(([sourceType, displayName]) => {
    if (!isGranted(session, sourceType)) return consentRequired(sourceType, displayName)
    return refresh ? refreshed(session, sourceType, displayName) : state(sourceType, displayName)
  }),
  demoOnly: true,
})

export const mockDataConnectionProvider: DataConnectionProvider = {
  async list(sessionId, signal) {
    await wait(signal)
    return response(await getSession(sessionId, signal), false)
  },
  async refresh(sessionId, signal) {
    await wait(signal, 850)
    return response(await getSession(sessionId, signal), true)
  },
  async retrySource(sessionId, sourceType, signal) {
    await wait(signal, 700)
    const session = await getSession(sessionId, signal)
    const source = response(session, true).dataSources.find((item) => item.sourceType === sourceType)
    if (!source) throw {
      code: 'DEMO_SOURCE_NOT_FOUND',
      message: '재시도할 데이터 항목을 찾지 못했습니다.',
      requestId: 'demo-source-missing',
      retryable: false,
    } satisfies ApiError
    return source
  },
}
