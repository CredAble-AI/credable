import { liveEvidenceResolutionProvider } from '../api/evidenceResolutionClient'
import { selectProvider } from '../config/providerMode'
import { mockEvidenceResolutionProvider } from '../mocks/evidenceResolutionProvider'

export const evidenceResolutionProvider = selectProvider(mockEvidenceResolutionProvider, liveEvidenceResolutionProvider)
