export type DemoProfileType = string

export interface DemoProfile {
  demoProfileId: string
  displayName: string
  description: string
}

export interface ConsentSelections {
  required: Record<'customerIdentity' | 'accountSummary' | 'creditInformation', boolean>
  optional: Record<'submittedDocuments' | 'otherInstitutions' | 'partnerData', boolean>
}

/** Frontend-only temporary contract. This is not a backend API schema. */
export interface CustomerSession {
  sessionId: string
  selectedProfileType: DemoProfileType
  demoProfile: DemoProfile
  consents: ConsentSelections
  demoOnly: true
  createdAt: string
  updatedAt: string
}

export const emptyConsents = (): ConsentSelections => ({
  required: { customerIdentity: false, accountSummary: false, creditInformation: false },
  optional: { submittedDocuments: false, otherInstitutions: false, partnerData: false },
})
