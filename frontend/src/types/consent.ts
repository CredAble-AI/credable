export type ConsentSourceType = 'BANK_INTERNAL' | 'CREDIT_INFORMATION' | 'CUSTOMER_SUBMITTED' | 'EXTERNAL_CONNECTED'
export type ConsentStatus = 'PENDING' | 'GRANTED' | 'WITHDRAWN'

export interface ConsentState {
  sourceType: ConsentSourceType
  displayName: string
  description: string
  required: boolean | null
  status: ConsentStatus
  grantedAt: string | null
  withdrawnAt: string | null
  updatedAt: string | null
  scopeVersion: string
  demoOnly: true
}

export interface ConsentListResponse {
  sessionId: string
  consents: ConsentState[]
  scopeVersion: string
  demoOnly: true
}
