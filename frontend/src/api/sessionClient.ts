import type { ApiError } from '../types/api'
import { emptyConsents, type ConsentSelections, type CustomerSession, type DemoProfile } from '../types/customerSession'

export interface CustomerSessionProvider {
  listDemoProfiles(signal: AbortSignal): Promise<DemoProfile[]>
  create(demoProfileId: string, signal: AbortSignal): Promise<CustomerSession>
  get(signal: AbortSignal): Promise<CustomerSession | null>
  updateConsents(consents: ConsentSelections, signal: AbortSignal): Promise<CustomerSession | null>
}

export const normalizeSessionError = (error: unknown): ApiError => {
  if (typeof error === 'object' && error !== null && 'code' in error && 'message' in error && 'retryable' in error) return error as ApiError
  return { code: 'SESSION_REQUEST_FAILED', message: '세션 정보를 확인하지 못했습니다.', retryable: true }
}

const apiRequest = async <T,>(url: string, signal: AbortSignal, init: RequestInit = {}): Promise<T> => {
  const response = await fetch(url, { ...init, signal })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { error?: ApiError } | null
    throw body?.error ?? { code: 'SESSION_REQUEST_FAILED', message: '세션 요청에 실패했습니다.', requestId: response.headers.get('x-request-id') ?? undefined, retryable: response.status >= 500 } satisfies ApiError
  }
  return response.json() as Promise<T>
}

const SESSION_ID_KEY = 'credable.session-id'
const readSessionId = () => localStorage.getItem(SESSION_ID_KEY)
const writeSessionId = (sessionId: string) => localStorage.setItem(SESSION_ID_KEY, sessionId)
const clearSessionId = () => localStorage.removeItem(SESSION_ID_KEY)

interface BackendCustomerSession {
  sessionId: string
  demoProfile: DemoProfile
  status: string
  createdAt: string
  dataVersion: string
  demoOnly: true
}
interface DemoProfileCatalogResponse { dataVersion: string; profiles: DemoProfile[]; demoOnly: true }
interface DemoSessionCreateResponse { sessionId: string; session: BackendCustomerSession }
interface CustomerSessionState { session: BackendCustomerSession }
interface ConsentState { sourceType: 'BANK_INTERNAL' | 'CREDIT_INFORMATION' | 'CUSTOMER_SUBMITTED' | 'EXTERNAL_CONNECTED'; status: 'PENDING' | 'GRANTED' | 'WITHDRAWN' }
interface ConsentListResponse { sessionId: string; consents: ConsentState[]; scopeVersion: string; demoOnly: true }

const toCustomerSession = (session: BackendCustomerSession, consents: ConsentSelections): CustomerSession => ({
  sessionId: session.sessionId,
  selectedProfileType: session.demoProfile.demoProfileId,
  demoProfile: session.demoProfile,
  consents,
  demoOnly: true,
  createdAt: session.createdAt,
  updatedAt: session.createdAt,
})

// Backend has no direct equivalent of the frontend's required/optional consent grouping (its own
// `required` field is not yet populated - see ConsentSelections). This only maps actual GRANTED
// status onto the existing sourceType grouping already used by mocks/dataConnectionProvider.ts,
// it never infers required/optional from backend data.
const toConsentSelections = (consents: ConsentState[]): ConsentSelections => {
  const granted = new Set(consents.filter((item) => item.status === 'GRANTED').map((item) => item.sourceType))
  return {
    required: {
      customerIdentity: granted.has('BANK_INTERNAL'),
      accountSummary: granted.has('BANK_INTERNAL'),
      creditInformation: granted.has('CREDIT_INFORMATION'),
    },
    optional: {
      submittedDocuments: granted.has('CUSTOMER_SUBMITTED'),
      otherInstitutions: granted.has('EXTERNAL_CONNECTED'),
      partnerData: granted.has('EXTERNAL_CONNECTED'),
    },
  }
}

export const liveCustomerSessionProvider: CustomerSessionProvider = {
  async listDemoProfiles(signal) {
    const response = await apiRequest<DemoProfileCatalogResponse>('/v1/demo-profiles', signal)
    return response.profiles
  },
  async create(demoProfileId, signal) {
    const response = await apiRequest<DemoSessionCreateResponse>('/v1/sessions/demo', signal, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ demoProfileId }),
    })
    writeSessionId(response.sessionId)
    return toCustomerSession(response.session, emptyConsents())
  },
  async get(signal) {
    const sessionId = readSessionId()
    if (!sessionId) return null
    try {
      const [sessionState, consentList] = await Promise.all([
        apiRequest<CustomerSessionState>(`/v1/sessions/${encodeURIComponent(sessionId)}`, signal),
        apiRequest<ConsentListResponse>(`/v1/sessions/${encodeURIComponent(sessionId)}/consents`, signal),
      ])
      return toCustomerSession(sessionState.session, toConsentSelections(consentList.consents))
    } catch {
      if (!signal.aborted) clearSessionId()
      return null
    }
  },
  async updateConsents(consents, signal) {
    const sessionId = readSessionId()
    if (!sessionId) return null
    // No backend grant/withdraw call is wired yet, so this only carries the customer's selection
    // forward to the next screen; a refresh restores the backend's actual (currently PENDING) state via get().
    const sessionState = await apiRequest<CustomerSessionState>(`/v1/sessions/${encodeURIComponent(sessionId)}`, signal)
    return toCustomerSession(sessionState.session, consents)
  },
}
