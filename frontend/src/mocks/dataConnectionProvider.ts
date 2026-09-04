import type { DataConnectionProvider } from '../api/dataConnectionClient'
import type { ApiError } from '../types/api'
import type { ConsentSourceType, DataConnectionRequest, DataConnectionResult, DataSourceState } from '../types/dataConnection'

const wait = (signal: AbortSignal, milliseconds = 650) => new Promise<void>((resolve, reject) => {
  const timer = window.setTimeout(resolve, milliseconds)
  signal.addEventListener('abort', () => { window.clearTimeout(timer); reject(new DOMException('Aborted', 'AbortError')) }, { once: true })
})

const selected = (request: DataConnectionRequest, sourceType: ConsentSourceType) => {
  if (sourceType === 'CUSTOMER_SUBMITTED') return request.consents.optional.submittedDocuments
  if (sourceType === 'EXTERNAL_CONNECTED') return request.consents.optional.otherInstitutions || request.consents.optional.partnerData
  return true
}

const state = (sourceType: ConsentSourceType, displayName: string, overrides: Partial<DataSourceState> = {}): DataSourceState => ({
  sourceType,
  displayName,
  retrievalStatus: 'RETRIEVED',
  verificationStatus: 'VERIFIED',
  observedAt: '2026-08-31T23:59:59+09:00',
  retrievedAt: '2026-09-04T10:30:00+09:00',
  dataVersion: 'synthetic-demo-v1',
  demoOnly: true,
  ...overrides,
})

const notSelected = (sourceType: ConsentSourceType, displayName: string): DataSourceState => state(sourceType, displayName, {
  retrievalStatus: 'CONSENT_REQUIRED',
  verificationStatus: 'NOT_STARTED',
  observedAt: null,
  retrievedAt: null,
  dataVersion: null,
  reasonCode: 'OPTIONAL_CONSENT_NOT_GRANTED',
})

const fixture = (request: DataConnectionRequest): DataConnectionResult => {
  const sources: DataSourceState[] = [
    state('BANK_INTERNAL', '은행 내부 데이터'),
    state('CREDIT_INFORMATION', '정식 조회 신용정보'),
  ]

  if (!selected(request, 'CUSTOMER_SUBMITTED')) sources.push(notSelected('CUSTOMER_SUBMITTED', '고객 제출 데이터'))
  else if (request.profileType === 'startup') sources.push(state('CUSTOMER_SUBMITTED', '고객 제출 재무 자료', { verificationStatus: 'STALE', observedAt: '2025-12-31T23:59:59+09:00', reasonCode: 'DEMO_OBSERVATION_STALE' }))
  else sources.push(state('CUSTOMER_SUBMITTED', '고객 제출 사업 자료'))

  if (!selected(request, 'EXTERNAL_CONNECTED')) sources.push(notSelected('EXTERNAL_CONNECTED', '외부 연결 데이터'))
  else if (request.profileType === 'startup') sources.push(state('EXTERNAL_CONNECTED', '제휴 외부 데이터', { retrievalStatus: 'FAILED', verificationStatus: 'NOT_STARTED', observedAt: null, dataVersion: null, reasonCode: 'DEMO_PARTNER_UNAVAILABLE' }))
  else sources.push(state('EXTERNAL_CONNECTED', '외부 연결 데이터'))

  return {
    sessionId: request.sessionId,
    dataSources: sources,
    demoOnly: true,
    canProceed: true,
    proceedReason: '필수 데이터 확인이 완료되었습니다. 선택 데이터는 연결하지 않고 진행할 수 있습니다.',
  }
}

export const mockDataConnectionProvider: DataConnectionProvider = {
  async list(request, signal) {
    await wait(signal)
    return fixture(request)
  },
  async refresh(request, signal) {
    await wait(signal, 850)
    return fixture(request)
  },
  async retrySource(request, sourceType, signal) {
    await wait(signal, 700)
    const source = fixture(request).dataSources.find((item) => item.sourceType === sourceType)
    if (!source) throw { code: 'DEMO_SOURCE_NOT_FOUND', message: '재시도할 데이터 항목을 찾지 못했습니다.', requestId: 'demo-source-missing', retryable: false } satisfies ApiError
    return source
  },
}
