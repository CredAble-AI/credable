import type { CustomerSessionProvider } from '../api/sessionClient'
import type { ApiError } from '../types/api'
import { emptyConsents, type BusinessBorrowerType, type ConsentSelections, type CustomerSession, type DemoProfile } from '../types/customerSession'

const STORAGE_KEY = 'credable.customer-session'
const SESSION_TTL_MS = 24 * 60 * 60 * 1000

const wait = (signal: AbortSignal, milliseconds = 300) => new Promise<void>((resolve, reject) => {
  const timer = window.setTimeout(resolve, milliseconds)
  signal.addEventListener('abort', () => { window.clearTimeout(timer); reject(new DOMException('Aborted', 'AbortError')) }, { once: true })
})

const mockProfiles: DemoProfile[] = [
  { demoProfileId: 'small-business', businessBorrowerType: 'SOLE_PROPRIETOR', displayName: '개인사업자', description: '개업 초기 소상공인을 예시로 한 개인사업자 합성 Demo 사례' },
  { demoProfileId: 'startup', businessBorrowerType: 'CORPORATION', displayName: '법인사업자', description: '설립 초기 스타트업을 예시로 한 법인사업자 합성 Demo 사례' },
]

const isBusinessBorrowerType = (value: unknown): value is BusinessBorrowerType => value === 'SOLE_PROPRIETOR' || value === 'CORPORATION'

const isDemoProfile = (value: unknown): value is DemoProfile => {
  if (!value || typeof value !== 'object') return false
  const profile = value as Partial<DemoProfile>
  return typeof profile.demoProfileId === 'string'
    && isBusinessBorrowerType(profile.businessBorrowerType)
    && typeof profile.displayName === 'string'
    && typeof profile.description === 'string'
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
  async create(businessBorrowerType, signal) {
    await wait(signal)
    const profile = mockProfiles.find((item) => item.businessBorrowerType === businessBorrowerType)
    if (!profile) throw { code: 'BUSINESS_BORROWER_TYPE_NOT_FOUND', message: '선택한 사업자 유형을 찾을 수 없습니다.', retryable: false } satisfies ApiError
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
