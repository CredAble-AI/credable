import { emptyConsents, type ConsentSelections, type CustomerSession, type DemoProfileType } from '../types/customerSession'

const STORAGE_KEY = 'credable.customer-session'
const SESSION_TTL_MS = 24 * 60 * 60 * 1000

const isProfileType = (value: unknown): value is DemoProfileType => value === 'SMALL_BUSINESS' || value === 'STARTUP'
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
    && isProfileType(session.selectedProfileType)
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

export const customerSessionProvider = {
  get: read,
  create(selectedProfileType: DemoProfileType): CustomerSession {
    localStorage.removeItem(STORAGE_KEY)
    const now = new Date().toISOString()
    const session: CustomerSession = {
      sessionId: crypto.randomUUID(),
      selectedProfileType,
      consents: emptyConsents(),
      demoOnly: true,
      createdAt: now,
      updatedAt: now,
    }
    write(session)
    return session
  },
  updateConsents(consents: ConsentSelections): CustomerSession | null {
    const session = read()
    if (!session) return null
    const updated = { ...session, consents, updatedAt: new Date().toISOString() }
    write(updated)
    return updated
  },
}
