import { liveEvidenceSelectionProvider } from '../api/evidenceSelectionClient'
import { selectProvider } from '../config/providerMode'
import { mockEvidenceSelectionProvider } from '../mocks/evidenceSelectionProvider'

export const evidenceSelectionProvider = selectProvider(mockEvidenceSelectionProvider, liveEvidenceSelectionProvider)
