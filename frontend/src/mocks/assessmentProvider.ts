import type { AssessmentProvider } from '../api/assessmentClient'
import type { AssessmentRequest, AssessmentResult } from '../types/assessment'

const results = new Map<string, AssessmentResult>()
const wait = (signal: AbortSignal, milliseconds = 700) => new Promise<void>((resolve, reject) => {
  const timer = window.setTimeout(resolve, milliseconds)
  signal.addEventListener('abort', () => { window.clearTimeout(timer); reject(new DOMException('Aborted', 'AbortError')) }, { once: true })
})

const notRun = (request: AssessmentRequest): AssessmentResult => ({
  sessionId: request.sessionId,
  assessment: { status: 'NOT_RUN', demoOnly: true },
  dataSummary: [], excludedData: [], canProceed: false,
  proceedReason: '보완 평가 실행 전입니다.', resultMode: 'MOCK',
})

const fixture = (request: AssessmentRequest): AssessmentResult => {
  const calculatedAt = '2026-09-04T11:00:00+09:00'
  if (request.profileType === 'STARTUP') return {
    sessionId: request.sessionId,
    assessment: { assessmentId: `asm_demo_${request.sessionId}`, status: 'INSUFFICIENT_DATA', calculatedAt, inputSnapshotId: 'dss_demo_startup_v1', modelVersion: null, reasonCode: 'DEMO_VERIFIED_DATA_INSUFFICIENT', demoOnly: true },
    summary: '현재 연결·검증된 데이터만으로는 보완 평가 결과를 산출할 수 없습니다.',
    dataSummary: ['은행 보유 데이터 확인', '고객 제출 재무 자료 기준시점 확인 필요'],
    excludedData: ['검증이 완료되지 않은 제휴 외부 데이터'],
    canProceed: false,
    proceedReason: '이는 신용이 낮거나 대출 자격이 없다는 의미가 아닙니다.',
    resultMode: 'MOCK',
  }
  return {
    sessionId: request.sessionId,
    assessment: { assessmentId: `asm_demo_${request.sessionId}`, status: 'COMPLETED', calculatedAt, inputSnapshotId: 'dss_demo_small_business_v1', modelVersion: 'demo-small-business-assessment-v1', reasonCode: null, demoOnly: true },
    summary: '은행 보유 데이터와 고객이 동의한 확인 자료를 기준으로 보완 평가 처리가 완료되었습니다.',
    dataSummary: ['은행 내부 고객·계좌 요약', '정식 절차로 조회한 신용정보', '고객이 동의한 제출 자료'],
    excludedData: ['선택하지 않은 외부 연결 데이터'],
    canProceed: true,
    proceedReason: 'Demo 상품 조건 비교 단계로 이동할 수 있습니다.',
    resultMode: 'MOCK',
  }
}

export const mockAssessmentProvider: AssessmentProvider = {
  async get(request, signal) {
    await wait(signal, 450)
    return results.get(request.sessionId) ?? notRun(request)
  },
  async run(request, signal) {
    await wait(signal, 900)
    const result = fixture(request)
    results.set(request.sessionId, result)
    return result
  },
}
