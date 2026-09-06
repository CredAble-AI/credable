import type { ConsentSourceType } from './consent'

export type EvidenceCollectionMode = 'DEMO_FILE_UPLOAD' | 'DEMO_CONNECTION' | 'UNAVAILABLE'
export type EvidenceSubmissionRequirementStatus = 'READY' | 'CONSENT_REQUIRED' | 'UNAVAILABLE'

export interface EvidenceSubmissionRequirement {
  status: EvidenceSubmissionRequirementStatus
  reasonCode: string | null
  consentSourceType: ConsentSourceType
}

export interface DemoEvidenceFileDescriptor {
  demoFileId: string
  displayName: string
  description: string
  fileName: string
  contentType: 'application/pdf'
  sizeBytes: number
  downloadUrl: string
}

export interface EvidenceUploadPolicy {
  allowedContentTypes: string[]
  allowedExtensions: string[]
  maxSizeBytes: number
}

export interface EvidenceSubmissionOption {
  sessionId: string
  selectionId: string
  evidenceType: string
  collectionMode: EvidenceCollectionMode
  submissionRequirement: EvidenceSubmissionRequirement
  demoFile: DemoEvidenceFileDescriptor | null
  uploadPolicy: EvidenceUploadPolicy | null
  demoOnly: true
}

export interface UploadedEvidenceFile {
  demoFileId: string
  fileName: string
  contentType: 'application/pdf'
  sizeBytes: number
  sha256: string
}

export interface EvidenceSubmissionState {
  submissionId: string
  selectionId: string
  evidenceType: string
  sourceType: ConsentSourceType
  submissionMode: 'DEMO_FIXTURE_REFERENCE' | 'DEMO_FILE_UPLOAD'
  status: 'RECEIVED'
  submittedAt: string
  observedAt: string
  submissionSnapshotHash: string
  dataVersion: string
  uploadedFile: UploadedEvidenceFile | null
  demoOnly: true
}

export interface EvidenceSubmissionResponse {
  sessionId: string
  submission: EvidenceSubmissionState | null
}
