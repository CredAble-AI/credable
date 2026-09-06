import type { AssessmentProvider } from '../api/assessmentClient'
import type { PolicyBoundaryProvider } from '../api/policyBoundaryClient'
import type { ApiError } from '../types/api'
import type { AssessmentRequest, AssessmentResponse } from '../types/assessment'
import type { PolicyBoundaryCheckResponse } from '../types/policyBoundary'

const assessmentResults = new Map<string, AssessmentResponse>()
const boundaryResults = new Map<string, PolicyBoundaryCheckResponse>()
export const getMockAssessmentResult = (sessionId: string) => assessmentResults.get(sessionId)?.assessment ?? null
export const getMockPolicyBoundaryResult = (sessionId: string) => boundaryResults.get(sessionId)?.boundaryCheck ?? null
const wait = (signal: AbortSignal, milliseconds = 700) => new Promise<void>((resolve, reject) => {
  const timer = window.setTimeout(resolve, milliseconds)
  signal.addEventListener('abort', () => { window.clearTimeout(timer); reject(new DOMException('Aborted', 'AbortError')) }, { once: true })
})

const notRun = (request: AssessmentRequest): AssessmentResponse => ({
  sessionId: request.sessionId,
  assessment: {
    assessmentId: null,
    status: 'NOT_RUN',
    calculatedAt: null,
    inputSnapshotId: null,
    modelVersion: null,
    reasonCode: null,
    uncertainty: null,
    demoOnly: true,
  },
})

const fixture = (request: AssessmentRequest): AssessmentResponse => {
  const calculatedAt = '2026-09-04T11:00:00+09:00'
  if (request.profileType === 'startup') return {
    sessionId: request.sessionId,
    assessment: {
      assessmentId: `asm_demo_${request.sessionId}`,
      status: 'INSUFFICIENT_DATA',
      calculatedAt,
      inputSnapshotId: 'dss_demo_startup_v1',
      modelVersion: null,
      reasonCode: 'DEMO_VERIFIED_DATA_INSUFFICIENT',
      uncertainty: null,
      demoOnly: true,
    },
  }
  return {
    sessionId: request.sessionId,
    assessment: {
      assessmentId: `asm_demo_${request.sessionId}`,
      status: 'COMPLETED',
      calculatedAt,
      inputSnapshotId: 'dss_demo_small_business_v1',
      modelVersion: 'demo-small-business-assessment-v1',
      reasonCode: null,
      uncertainty: {
        pointEstimate: null,
        lowerBound: null,
        upperBound: null,
        gradeSet: ['DEMO_GRADE_B', 'DEMO_GRADE_C'],
        calibrationMode: 'RULE_TABLE',
        calibrationVersion: 'demo-uncertainty-rule-table-v1',
        demoOnly: true,
      },
      demoOnly: true,
    },
  }
}

export const mockAssessmentProvider: AssessmentProvider = {
  async get(request, signal) {
    await wait(signal, 450)
    return assessmentResults.get(request.sessionId) ?? notRun(request)
  },
  async run(request, signal) {
    await wait(signal, 900)
    const result = fixture(request)
    assessmentResults.set(request.sessionId, result)
    boundaryResults.delete(request.sessionId)
    return result
  },
}

export const mockPolicyBoundaryProvider: PolicyBoundaryProvider = {
  async get(sessionId, signal) {
    await wait(signal, 350)
    return boundaryResults.get(sessionId) ?? { sessionId, boundaryCheck: null }
  },
  async check(sessionId, signal) {
    await wait(signal, 650)
    const assessment = assessmentResults.get(sessionId)?.assessment
    if (!assessment || assessment.status !== 'COMPLETED' || !assessment.uncertainty || !assessment.assessmentId || !assessment.inputSnapshotId) throw {
      code: 'ASSESSMENT_NOT_READY_FOR_BOUNDARY_CHECK',
      message: '완료된 기준평가가 있어야 정책 경계를 확인할 수 있습니다.',
      retryable: false,
    } satisfies ApiError
    const result: PolicyBoundaryCheckResponse = {
      sessionId,
      boundaryCheck: {
        boundaryCheckId: `pbc_demo_${sessionId}`,
        assessmentId: assessment.assessmentId,
        checkedAt: '2026-09-04T11:01:00+09:00',
        decision: {
          status: 'AMBIGUOUS',
          possibleRoutes: ['DEMO_PATH_1', 'DEMO_PATH_2'],
          crossedBoundaryCodes: ['DEMO_BOUNDARY_1_2'],
          stopReason: null,
          underwriterRequired: false,
        },
        inputSnapshotId: assessment.inputSnapshotId,
        calibrationVersion: assessment.uncertainty.calibrationVersion,
        policyVersion: 'demo-policy-boundary-v1',
        demoOnly: true,
      },
    }
    boundaryResults.set(sessionId, result)
    return result
  },
}
