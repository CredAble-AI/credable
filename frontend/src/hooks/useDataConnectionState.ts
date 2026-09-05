import { liveDataConnectionProvider } from '../api/dataConnectionClient'
import { selectProvider } from '../config/providerMode'
import { mockDataConnectionProvider } from '../mocks/dataConnectionProvider'

export const dataConnectionProvider = selectProvider(mockDataConnectionProvider, liveDataConnectionProvider)
