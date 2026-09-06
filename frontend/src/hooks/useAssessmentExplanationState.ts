import { liveAssessmentExplanationProvider } from '../api/assessmentExplanationClient'
import { selectProvider } from '../config/providerMode'
import { mockAssessmentExplanationProvider } from '../mocks/assessmentExplanationProvider'

export const assessmentExplanationProvider = selectProvider(mockAssessmentExplanationProvider, liveAssessmentExplanationProvider)
