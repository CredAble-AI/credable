import { liveAdminEvidenceBurdenProvider } from '../api/adminEvidenceBurdenClient'
import { selectProvider } from '../config/providerMode'
import { mockAdminEvidenceBurdenProvider } from '../mocks/adminEvidenceBurdenProvider'

export const adminEvidenceBurdenProvider = selectProvider(mockAdminEvidenceBurdenProvider, liveAdminEvidenceBurdenProvider)
