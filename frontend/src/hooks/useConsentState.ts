import { liveConsentProvider } from '../api/consentClient'
import { selectProvider } from '../config/providerMode'
import { mockConsentProvider } from '../mocks/consentProvider'

export const consentProvider = selectProvider(mockConsentProvider, liveConsentProvider)
