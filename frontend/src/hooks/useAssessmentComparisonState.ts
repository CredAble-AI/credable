import { liveAssessmentComparisonProvider } from '../api/assessmentComparisonClient'
import { selectProvider } from '../config/providerMode'
import { mockAssessmentComparisonProvider } from '../mocks/assessmentComparisonProvider'

export const assessmentComparisonProvider = selectProvider(mockAssessmentComparisonProvider, liveAssessmentComparisonProvider)
