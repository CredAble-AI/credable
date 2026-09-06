import type { CustomerSessionProvider } from '../api/sessionClient'
import type { ApiError } from '../types/api'
import { emptyConsents, type BusinessBorrowerType, type ConsentSelections, type CustomerSession, type DemoProfile } from '../types/customerSession'

const STORAGE_KEY = 'credable.customer-session'
const SESSION_TTL_MS = 24 * 60 * 60 * 1000

const wait = (signal: AbortSignal, milliseconds = 300) => new Promise<void>((resolve, reject) => {
  const timer = window.setTimeout(resolve, milliseconds)
  signal.addEventListener('abort', () => { window.clearTimeout(timer); reject(new DOMException('Aborted', 'AbortError')) }, { once: true })
})

const ambiguousScenario = { scenarioLabel: '정책 경계에 걸린 사례', scenarioSummary: '기존 평가 구간이 두 정책 경로에 걸쳐 있어 최소 증빙 한 건을 요청하는 흐름을 확인합니다.' }
const mockProfiles: DemoProfile[] = [
  { demoProfileId: 'small-business', businessBorrowerType: 'SOLE_PROPRIETOR', displayName: '개인사업자', description: '개업 초기 소상공인을 예시로 한 개인사업자 합성 Demo 사례', ...ambiguousScenario },
  { demoProfileId: 'small-business-stable', businessBorrowerType: 'SOLE_PROPRIETOR', displayName: '개인사업자', description: '기존 평가만으로 처리 경로가 확인되는 개인사업자 합성 Demo 사례', scenarioLabel: '추가 증빙이 필요 없는 사례', scenarioSummary: '기존 평가만으로 하나의 정책 경로가 확인되어 추가 자료를 요청하지 않는 흐름을 확인합니다.' },
  { demoProfileId: 'startup', businessBorrowerType: 'CORPORATION', displayName: '법인사업자', description: '설립 초기 스타트업을 예시로 한 법인사업자 합성 Demo 사례', ...ambiguousScenario },
  { demoProfileId: 'startup-policy-blocked', businessBorrowerType: 'CORPORATION', displayName: '법인사업자', description: '대출정책상 제한이 확인된 법인사업자 합성 Demo 사례', scenarioLabel: '대출정책상 제한 사례', scenarioSummary: '추가 증빙으로 해소할 수 없는 정책상 제한을 안내하고 증빙 수집을 시작하지 않는 흐름을 확인합니다.' },
]

const isBusinessBorrowerType = (value: unknown): value is BusinessBorrowerType => value === 'SOLE_PROPRIETOR' || value === 'CORPORATION'

const isDemoProfile = (value: unknown): value is DemoProfile => {
  if (!value || typeof value !== 'object') return false
  const profile = value as Partial<DemoProfile>
  return typeof profile.demoProfileId === 'string'
    && isBusinessBorrowerType(profile.businessBorrowerType)
    && typeof profile.displayName === 'string'
    && typeof profile.description === 'string'
    && typeof profile.scenarioLabel === 'string'
    && typeof profile.scenarioSummary === 'string'
}
const hasBooleanValues = (value: unknown, keys: string[]) => {
  if (!value || typeof value !== 'object') return false
  const record = value as Record<string, unknown>
  return keys.every((key) => typeof record[key] === 'boolean')
}

const isValidSession = (value: unknown): value is CustomerSession => {
  if (!value || typeof value !== 'object') return false
  const session = value as Partial<CustomerSession>
  const updatedAt = typeof session.updatedAt === 'string' ? Date.parse(session.updatedAt) : Number.NaN
  return typeof session.sessionId === 'string'
    && typeof session.selectedProfileType === 'string' && session.selectedProfileType.length > 0
    && isDemoProfile(session.demoProfile)
    && session.demoOnly === true
    && typeof session.createdAt === 'string'
    && Number.isFinite(updatedAt)
    && hasBooleanValues(session.consents?.required, ['customerIdentity', 'accountSummary', 'creditInformation'])
    && hasBooleanValues(session.consents?.optional, ['submittedDocuments', 'otherInstitutions', 'partnerData'])
}

const read = (): CustomerSession | null => {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const session: unknown = JSON.parse(raw)
    if (!isValidSession(session) || Date.now() - Date.parse(session.updatedAt) > SESSION_TTL_MS) {
      localStorage.removeItem(STORAGE_KEY)
      return null
    }
    return session
  } catch {
    localStorage.removeItem(STORAGE_KEY)
    return null
  }
}

const write = (session: CustomerSession) => localStorage.setItem(STORAGE_KEY, JSON.stringify(session))

export const mockCustomerSessionProvider: CustomerSessionProvider = {
  async listDemoProfiles(signal) {
    await wait(signal)
    return mockProfiles
  },
  async create(demoProfileId, signal) {
    await wait(signal)
    const profile = mockProfiles.find((item) => item.demoProfileId === demoProfileId)
    if (!profile) throw { code: 'DEMO_PROFILE_NOT_FOUND', message: '선택한 시연 사례를 찾을 수 없습니다.', retryable: false } satisfies ApiError
    localStorage.removeItem(STORAGE_KEY)
    const now = new Date().toISOString()
    const session: CustomerSession = {
      sessionId: crypto.randomUUID(),
      selectedProfileType: profile.demoProfileId,
      demoProfile: profile,
      consents: emptyConsents(),
      demoOnly: true,
      createdAt: now,
      updatedAt: now,
    }
    write(session)
    return session
  },
  async get(signal) {
    await wait(signal, 150)
    return read()
  },
  async updateConsents(consents: ConsentSelections, signal) {
    await wait(signal, 150)
    const session = read()
    if (!session) return null
    const updated = { ...session, consents, updatedAt: new Date().toISOString() }
    write(updated)
    return updated
  },
}
