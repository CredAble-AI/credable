import { liveEvidenceQualityProvider } from '../api/evidenceQualityClient'
import { selectProvider } from '../config/providerMode'
import { mockEvidenceQualityProvider } from '../mocks/evidenceQualityProvider'

export const evidenceQualityProvider = selectProvider(mockEvidenceQualityProvider, liveEvidenceQualityProvider)
