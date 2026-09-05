import { liveAssessmentProvider } from '../api/assessmentClient'
import { livePolicyBoundaryProvider } from '../api/policyBoundaryClient'
import { selectProvider } from '../config/providerMode'
import { mockAssessmentProvider, mockPolicyBoundaryProvider } from '../mocks/assessmentProvider'

export const assessmentProvider = selectProvider(mockAssessmentProvider, liveAssessmentProvider)
export const policyBoundaryProvider = selectProvider(mockPolicyBoundaryProvider, livePolicyBoundaryProvider)
