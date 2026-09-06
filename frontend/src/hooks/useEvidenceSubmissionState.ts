import { liveEvidenceSubmissionProvider } from '../api/evidenceSubmissionClient'
import { selectProvider } from '../config/providerMode'
import { mockEvidenceSubmissionProvider } from '../mocks/evidenceSubmissionProvider'

export const evidenceSubmissionProvider = selectProvider(mockEvidenceSubmissionProvider, liveEvidenceSubmissionProvider)
