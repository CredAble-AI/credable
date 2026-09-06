import type { ConsentSourceType, ConsentStatus } from './consent'

export interface EvidenceConsentScope {
  scopeVersion: string
  purposeCode: string
  purposeDescription: string
  dataCategories: string[]
  periodStart: string
  periodEnd: string
  required: true
}

export interface EvidenceConsentState extends EvidenceConsentScope {
  evidenceConsentId: string
  selectionId: string
  evidenceType: string
  sourceType: ConsentSourceType
  status: ConsentStatus
  grantedAt: string | null
  withdrawnAt: string | null
  updatedAt: string | null
  demoOnly: true
}

export interface EvidenceConsentResponse {
  sessionId: string
  selectionId: string
  consent: EvidenceConsentState
}
