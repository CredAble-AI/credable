export type CurrentDecision = 'DECLINED' | 'HELD'

export interface SecondLookCase {
  caseId: string
  applicationDate: string
  featureCutoffAt: string
  applicant: {
    businessName: string
    industry: string
    tenureMonths: number
  }
  application: {
    productType: string
    amount?: number
  }
  currentDecision: CurrentDecision
  declineReasonCodes: string[]
  demoOnly: boolean
}

export type DemoCaseType = 'BORDERLINE' | 'NO_DATA' | 'SUSPICIOUS' | 'HARD_STOP'

export interface CreateDemoCaseRequest { demoCaseType: DemoCaseType }
export interface CreateDemoCaseResponse { caseId: string; case: SecondLookCase }

export interface ApiError {
  code: string
  message: string
  requestId?: string
  retryable: boolean
}

export type EligibilityClass =
  | 'HARD_DECLINE'
  | 'SECOND_LOOK_ELIGIBLE'
  | 'DATA_QUALITY_ISSUE'

export interface EligibilityResult {
  classification: EligibilityClass
  reasons: string[]
  hardStops: string[]
  demoOnly: boolean
  evaluatedAt?: string
}

export interface CheckEligibilityRequest { caseId: string }

export type EvidenceAvailability =
  | 'BANK_INTERNAL'
  | 'CONSENT_REQUIRED'
  | 'PARTNER_REQUIRED'
  | 'CUSTOMER_UPLOAD'

export interface EvidenceCandidateScore {
  evidenceType: string
  availability: EvidenceAvailability
  policyRelevance: number
  gapCoverage: number
  crossCheckValue: number
  submissionBurden: number
  privacySensitivity: number
  utility: number
}

export interface EvidenceRecommendation {
  recommendedEvidenceType: string
  candidates: EvidenceCandidateScore[]
  rationaleCodes: string[]
  policyVersion?: string
  basedOn: Array<'APPLICATION' | 'DECLINE_REASON' | 'BANK_ACCOUNT' | 'CURRENT_EVIDENCE'>
  conditionalSources: Array<'OPEN_BANKING' | 'CARD_POS' | 'DELIVERY_SETTLEMENT'>
  inputSnapshotHash?: string
  recalculatedAt: string
  demoOnly: boolean
}

export interface EvidenceRequirementRequest { caseId: string; recomputeReason?: string }
