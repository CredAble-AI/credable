export type DemoProfileType = 'SMALL_BUSINESS' | 'STARTUP'

export interface ConsentSelections {
  required: Record<'customerIdentity' | 'accountSummary' | 'creditInformation', boolean>
  optional: Record<'submittedDocuments' | 'otherInstitutions' | 'partnerData', boolean>
}

/** Frontend-only temporary contract. This is not a backend API schema. */
export interface CustomerSession {
  sessionId: string
  selectedProfileType: DemoProfileType
  consents: ConsentSelections
  demoOnly: true
  createdAt: string
  updatedAt: string
}

export const emptyConsents = (): ConsentSelections => ({
  required: { customerIdentity: false, accountSummary: false, creditInformation: false },
  optional: { submittedDocuments: false, otherInstitutions: false, partnerData: false },
})
