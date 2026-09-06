import type { ConsentSourceType } from './consent'
import type { EvidenceCollectionMode } from './evidenceSubmission'

export type EvidenceAvailability = 'AVAILABLE' | 'REQUESTABLE' | 'CONSENT_REQUIRED' | 'UNAVAILABLE'
export type EvidenceSelectionStatus = 'SELECTED' | 'NOT_REQUIRED' | 'POLICY_BLOCKED' | 'HUMAN_REVIEW'

export interface SelectedEvidenceCandidate {
  evidenceType: string
  displayName: string
  description: string
  sourceType: ConsentSourceType
  collectionMode: EvidenceCollectionMode | null
  availability: EvidenceAvailability
  rationaleCodes: string[]
  demoOnly: true
}

export interface EvidenceSelectionState {
  selectionId: string
  boundaryCheckId: string
  resolutionId: string | null
  iteration: number
  status: EvidenceSelectionStatus
  selectedEvidence: SelectedEvidenceCandidate | null
  evaluatedCandidateCount: number
  stopReason: string | null
  underwriterRequired: boolean
  selectedAt: string
  calibrationVersion: string
  boundaryPolicyVersion: string
  selectionPolicyVersion: string
  demoOnly: true
}

export interface EvidenceSelectionResponse {
  sessionId: string
  selection: EvidenceSelectionState | null
}
