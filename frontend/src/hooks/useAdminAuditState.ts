import { liveAdminAuditProvider } from '../api/adminAuditClient'
import { selectProvider } from '../config/providerMode'
import { mockAdminAuditProvider } from '../mocks/adminAuditProvider'

export const adminAuditProvider = selectProvider(mockAdminAuditProvider, liveAdminAuditProvider)
