import { liveAssessmentReviewProvider } from '../api/assessmentReviewClient'
import { selectProvider } from '../config/providerMode'
import { mockAssessmentReviewProvider } from '../mocks/assessmentReviewProvider'

export const assessmentReviewProvider = selectProvider(mockAssessmentReviewProvider, liveAssessmentReviewProvider)
