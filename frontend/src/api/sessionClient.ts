import type { ApiError } from '../types/api'
import type { ConsentListResponse, ConsentState } from '../types/consent'
import { emptyConsents, type BusinessBorrowerType, type ConsentSelections, type CustomerSession, type DemoProfile } from '../types/customerSession'

export interface CustomerSessionProvider {
  listDemoProfiles(signal: AbortSignal): Promise<DemoProfile[]>
  create(businessBorrowerType: BusinessBorrowerType, signal: AbortSignal): Promise<CustomerSession>
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
    const error = body?.error ?? { code: 'SESSION_REQUEST_FAILED', message: '세션 요청에 실패했습니다.', requestId: response.headers.get('x-request-id') ?? undefined, retryable: response.status >= 500 } satisfies ApiError
    throw { ...error, status: response.status }
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
  async create(businessBorrowerType, signal) {
    const response = await apiRequest<DemoSessionCreateResponse>('/v1/sessions/demo', signal, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ businessBorrowerType }),
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
    } catch (caught) {
      if (signal.aborted) throw caught
      const error = normalizeSessionError(caught)
      const status = typeof caught === 'object' && caught !== null && 'status' in caught ? caught.status : null
      if (status === 404 || error.code === 'CUSTOMER_SESSION_NOT_FOUND') {
        clearSessionId()
        return null
      }
      throw error
    }
  },
  async updateConsents(consents, signal) {
    const sessionId = readSessionId()
    if (!sessionId) return null
    // Compatibility path for screens that still consume the legacy grouped consent shape.
    // New consent changes use liveConsentProvider's source-based grant/withdraw endpoints.
    const sessionState = await apiRequest<CustomerSessionState>(`/v1/sessions/${encodeURIComponent(sessionId)}`, signal)
    return toCustomerSession(sessionState.session, consents)
  },
}
