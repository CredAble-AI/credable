import { liveEvidenceConsentProvider } from '../api/evidenceConsentClient'
import { selectProvider } from '../config/providerMode'
import { mockEvidenceConsentProvider } from '../mocks/evidenceConsentProvider'

export const evidenceConsentProvider = selectProvider(mockEvidenceConsentProvider, liveEvidenceConsentProvider)
