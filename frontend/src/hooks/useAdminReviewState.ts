import { liveAdminReviewProvider } from '../api/adminReviewClient'
import { selectProvider } from '../config/providerMode'
import { mockAdminReviewProvider } from '../mocks/adminReviewProvider'

export const adminReviewProvider = selectProvider(mockAdminReviewProvider, liveAdminReviewProvider)
