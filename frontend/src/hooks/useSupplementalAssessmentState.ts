import { liveSupplementalAssessmentProvider } from '../api/supplementalAssessmentClient'
import { selectProvider } from '../config/providerMode'
import { mockSupplementalAssessmentProvider } from '../mocks/supplementalAssessmentProvider'

export const supplementalAssessmentProvider = selectProvider(mockSupplementalAssessmentProvider, liveSupplementalAssessmentProvider)
