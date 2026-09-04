import type { ConsentSelections, DemoProfileType } from './customerSession'

// Mirrors the current backend data-source contract. UI-only fields are kept in DataConnectionResult.
export type ConsentSourceType = 'BANK_INTERNAL' | 'CREDIT_INFORMATION' | 'CUSTOMER_SUBMITTED' | 'EXTERNAL_CONNECTED'
export type RetrievalStatus = 'CONSENT_REQUIRED' | 'NOT_REQUESTED' | 'RETRIEVED' | 'NO_DATA' | 'FAILED'
export type VerificationStatus = 'NOT_STARTED' | 'VERIFIED' | 'UNVERIFIED' | 'STALE'

export interface DataSourceState {
  sourceType: ConsentSourceType
  displayName: string
  retrievalStatus: RetrievalStatus
  verificationStatus: VerificationStatus
  observedAt?: string | null
  retrievedAt?: string | null
  dataVersion?: string | null
  reasonCode?: string | null
  demoOnly: true
}

export interface DataSourceListResponse {
  sessionId: string
  dataSources: DataSourceState[]
  demoOnly: true
}

export interface DataConnectionRequest {
  sessionId: string
  profileType: DemoProfileType
  consents: ConsentSelections
}

export interface DataConnectionResult extends DataSourceListResponse {
  canProceed: boolean | null
  proceedReason?: string
}
