import type { AssessmentExplanationProvider } from '../api/assessmentExplanationClient'
import type { AssessmentExplanationResponse, AssessmentExplanationState, ExplanationSection, ExplanationSourceReference } from '../types/assessmentExplanation'
import { getMockAssessmentComparisonResult } from './assessmentComparisonProvider'
import { getMockAssessmentResult, getMockPolicyBoundaryResult } from './assessmentProvider'
import { getMockEvidenceResolutionResult } from './evidenceResolutionProvider'
import { getMockSupplementalAssessmentResult } from './supplementalAssessmentProvider'

interface StoredExplanation { signature: string; response: AssessmentExplanationResponse }
const results = new Map<string, StoredExplanation>()
let explanationSequence = 0

const currentParts = (sessionId: string) => ({
  baseline: getMockAssessmentResult(sessionId),
  boundary: getMockPolicyBoundaryResult(sessionId),
  supplemental: getMockSupplementalAssessmentResult(sessionId),
  comparison: getMockAssessmentComparisonResult(sessionId),
  resolution: getMockEvidenceResolutionResult(sessionId),
})

const signatureOf = ({ baseline, boundary, supplemental, comparison, resolution }: ReturnType<typeof currentParts>) => {
  return [baseline?.assessmentId, boundary?.boundaryCheckId, supplemental?.supplementalAssessmentId, comparison?.comparisonId, resolution?.resolutionId].join('|')
}

const createExplanation = (sessionId: string, parts: ReturnType<typeof currentParts>): AssessmentExplanationState | null => {
  const { baseline, boundary, supplemental, comparison, resolution } = parts
  if (!baseline?.assessmentId || baseline.status === 'NOT_RUN') return null

  const sources: ExplanationSourceReference[] = [{
    sourceType: 'BASELINE_ASSESSMENT', sourceId: baseline.assessmentId, dataVersion: 'demo-v1', modelVersion: baseline.modelVersion, policyVersion: null,
  }]
  const sections: ExplanationSection[] = [{
    messageCode: baseline.status === 'COMPLETED' ? 'BASELINE_RESULT_AVAILABLE' : 'BASELINE_RESULT_INCOMPLETE',
    title: baseline.status === 'COMPLETED' ? '현재 확인된 평가 범위' : '기준평가가 완료되지 않았습니다',
    text: baseline.status === 'COMPLETED' ? '기존 CB·SCB와 은행 내부 평가 결과에서 확인된 범위를 기준으로 안내합니다. CredAble이 새로운 신용점수를 만든 결과가 아닙니다.' : '서버가 제공한 상태와 사유 코드를 확인하며 결과를 임의로 보완하지 않습니다.',
    sourceReferenceIds: [baseline.assessmentId],
  }]

  if (baseline.uncertainty && baseline.uncertainty.gradeSet.length > 1) {
    sections.push({ messageCode: 'BASELINE_UNCERTAINTY_PRESENT', title: '한 가지 결과로 확정되지 않은 이유', text: '현재 확인된 정보만으로는 복수의 평가 구간이 가능해 하나의 정책 경로로 확정할 수 없습니다.', sourceReferenceIds: [baseline.assessmentId] })
  }

  if (boundary) {
    sources.push({ sourceType: 'POLICY_BOUNDARY', sourceId: boundary.boundaryCheckId, dataVersion: 'demo-v1', modelVersion: null, policyVersion: boundary.policyVersion })
    const copy = boundary.decision.status === 'STABLE'
      ? ['POLICY_PATH_STABLE', '추가 자료 없이 확인 완료', '현재 평가 범위가 하나의 정책 경로에 속하므로 개인정보를 더 수집하지 않고 결과와 근거를 안내합니다.']
      : boundary.decision.status === 'AMBIGUOUS'
        ? ['POLICY_PATH_AMBIGUOUS', '다음으로 확인할 내용', '현재 경로를 구분하는 데 가장 영향이 큰 최소 증빙 한 건만 요청합니다. 검증을 통과한 정보만 보완평가에 반영합니다.']
        : ['POLICY_REVIEW_REQUIRED', '자동 판단을 중단한 이유', '정책 제한 또는 확인이 필요한 상태이므로 증빙을 더 요구하지 않고 자동 판단을 중단해 심사역에게 이관합니다.']
    sections.push({ messageCode: copy[0], title: copy[1], text: copy[2], sourceReferenceIds: [boundary.boundaryCheckId] })
  }

  if (supplemental) {
    sources.push({ sourceType: 'SUPPLEMENTAL_ASSESSMENT', sourceId: supplemental.supplementalAssessmentId, dataVersion: 'demo-v1', modelVersion: supplemental.modelVersion, policyVersion: null })
    sections.push({ messageCode: 'SUPPLEMENTAL_RESULT_AVAILABLE', title: '추가 증빙을 반영한 결과가 확인됐습니다', text: '품질검증을 통과한 증빙만 사용한 보완평가 상태를 설명합니다.', sourceReferenceIds: [supplemental.supplementalAssessmentId] })
  }
  if (comparison) {
    sources.push({ sourceType: 'ASSESSMENT_COMPARISON', sourceId: comparison.comparisonId, dataVersion: 'demo-v1', modelVersion: comparison.supplementalModelVersion, policyVersion: null })
    const narrowed = comparison.uncertaintyChange === 'NARROWED'
    sections.push({ messageCode: narrowed ? 'UNCERTAINTY_NARROWED' : 'UNCERTAINTY_UNCHANGED', title: narrowed ? '평가 결과 범위가 좁아졌습니다' : '평가 결과 범위가 유지됐습니다', text: narrowed ? '검증된 증빙 반영 전보다 가능한 결과 범위가 줄어든 것으로 확인됐습니다.' : '검증된 증빙을 반영했지만 가능한 결과 범위는 달라지지 않았습니다.', sourceReferenceIds: [comparison.comparisonId] })
  }
  if (resolution) {
    sources.push({ sourceType: 'EVIDENCE_RESOLUTION', sourceId: resolution.resolutionId, dataVersion: 'demo-v1', modelVersion: null, policyVersion: resolution.boundaryPolicyVersion })
    const resolved = resolution.status === 'RESOLVED'
    sections.push({ messageCode: resolved ? 'COLLECTION_RESOLVED' : 'MORE_EVIDENCE_REQUIRED', title: resolved ? '추가 증빙 수집이 종료됐습니다' : '추가 확인이 한 번 더 필요합니다', text: resolved ? '하나의 정책 경로가 확인되어 현재 단계의 추가 증빙 수집을 중단했습니다.' : '정책 경계의 불확실성이 남아 서버가 다음 최소 증빙 후보를 확인합니다.', sourceReferenceIds: [resolution.resolutionId] })
  }

  const targetAssessmentId = supplemental?.supplementalAssessmentId ?? baseline.assessmentId
  return {
    explanationId: `exp_demo_${sessionId}_${++explanationSequence}`,
    targetType: supplemental ? 'SUPPLEMENTAL_ASSESSMENT' : 'BASELINE_ASSESSMENT',
    targetAssessmentId,
    headline: sections.at(-1)?.title ?? sections[0].title,
    sections,
    cautionText: '이 설명은 서버가 확정한 구조화 결과를 요약한 것으로 대출 승인·부결, 금리 또는 한도를 의미하지 않습니다. 최종 금융 판단은 심사역이 수행합니다.',
    sourceReferences: sources,
    inputSnapshotHash: '0'.repeat(64),
    renderingMode: 'DEMO_TEMPLATE', fallbackApplied: false, fallbackReasonCode: null,
    providerVersion: 'demo-explanation-provider-v1', modelVersion: null, promptVersion: 'demo-explanation-prompt-v1', explanationPolicyVersion: 'assessment-explanation-policy-v1', dataVersion: 'demo-v1', generatedAt: new Date().toISOString(), demoOnly: true,
  }
}

export const mockAssessmentExplanationProvider: AssessmentExplanationProvider = {
  async get(sessionId, signal) {
    if (signal.aborted) throw new DOMException('Aborted', 'AbortError')
    const parts = currentParts(sessionId)
    const stored = results.get(sessionId)
    return stored?.signature === signatureOf(parts) ? stored.response : { sessionId, explanation: null }
  },
  async generate(sessionId, signal) {
    if (signal.aborted) throw new DOMException('Aborted', 'AbortError')
    const parts = currentParts(sessionId)
    const signature = signatureOf(parts)
    const existing = results.get(sessionId)
    if (existing?.signature === signature) return existing.response
    const response = { sessionId, explanation: createExplanation(sessionId, parts) }
    results.set(sessionId, { signature, response })
    return response
  },
}
