import { useCallback, useEffect, useRef, useState } from 'react'
import { normalizeSupplementalAssessmentError } from '../api/supplementalAssessmentClient'
import { supplementalAssessmentProvider } from '../hooks/useSupplementalAssessmentState'
import type { ApiError } from '../types/api'
import type { SupplementalAssessmentResponse, SupplementalAssessmentState } from '../types/supplementalAssessment'
import { assessmentGradeSetLabel } from '../utils/assessmentDisplay'
import AssessmentComparisonPanel from './AssessmentComparisonPanel'
import CustomerTechnicalDetails from './CustomerTechnicalDetails'

interface SupplementalAssessmentPanelProps { sessionId: string; submissionId: string; qualityCheckId: string }
type Phase = 'loading' | 'running' | 'idle'

const formatDate = (value: string) => new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))

function SupplementalAssessmentPanel({ sessionId, submissionId, qualityCheckId }: SupplementalAssessmentPanelProps) {
  const [assessment, setAssessment] = useState<SupplementalAssessmentState | null>(null)
  const [phase, setPhase] = useState<Phase>('loading')
  const [error, setError] = useState<ApiError | null>(null)
  const controllerRef = useRef<AbortController | null>(null)
  const sequenceRef = useRef(0)

  const acceptResponse = useCallback((response: SupplementalAssessmentResponse, required: boolean) => {
    if (response.sessionId !== sessionId) throw { code: 'SUPPLEMENTAL_ASSESSMENT_CONTEXT_MISMATCH', message: '현재 세션의 보완평가 상태를 확인할 수 없습니다.', retryable: true } satisfies ApiError
    const result = response.supplementalAssessment
    if (!result) {
      if (required) throw { code: 'SUPPLEMENTAL_ASSESSMENT_RESULT_MISSING', message: '서버가 보완평가 결과를 반환하지 않았습니다.', retryable: true } satisfies ApiError
      return null
    }
    if (result.submissionId !== submissionId) {
      if (required) throw { code: 'SUPPLEMENTAL_ASSESSMENT_CONTEXT_MISMATCH', message: '현재 제출과 일치하는 보완평가 결과를 확인할 수 없습니다.', retryable: true } satisfies ApiError
      return null
    }
    if (result.qualityCheckId !== qualityCheckId) throw { code: 'SUPPLEMENTAL_ASSESSMENT_CONTEXT_MISMATCH', message: '현재 품질검증과 일치하는 보완평가 결과를 확인할 수 없습니다.', retryable: true } satisfies ApiError
    return result
  }, [qualityCheckId, sessionId, submissionId])

  const request = useCallback(async (run: boolean) => {
    controllerRef.current?.abort()
    const controller = new AbortController(); controllerRef.current = controller
    const sequence = ++sequenceRef.current
    setPhase(run ? 'running' : 'loading'); setError(null)
    try {
      let response = run
        ? await supplementalAssessmentProvider.run(sessionId, submissionId, controller.signal)
        : await supplementalAssessmentProvider.get(sessionId, controller.signal)
      if (!run && !acceptResponse(response, false)) {
        if (sequence === sequenceRef.current) setPhase('running')
        response = await supplementalAssessmentProvider.run(sessionId, submissionId, controller.signal)
        run = true
      }
      const result = acceptResponse(response, run)
      if (sequence === sequenceRef.current) setAssessment(result)
    } catch (caught) {
      if (!controller.signal.aborted && sequence === sequenceRef.current) setError(normalizeSupplementalAssessmentError(caught))
    } finally {
      if (sequence === sequenceRef.current) setPhase('idle')
    }
  }, [acceptResponse, sessionId, submissionId])

  useEffect(() => {
    queueMicrotask(() => void request(false))
    return () => { sequenceRef.current += 1; controllerRef.current?.abort() }
  }, [request])

  if (phase !== 'idle' && !assessment) return <section className="supplemental-assessment supplemental-assessment--loading" aria-label="보완평가 진행 중"><span /><span /><p>확인된 자료를 반영해 기존 평가 범위를 다시 확인하고 있습니다.</p></section>

  if (!assessment) return <section className="supplemental-assessment" aria-labelledby="supplemental-title"><div className="supplemental-assessment__heading"><div><span>보완평가</span><h3 id="supplemental-title">보완평가를 완료하지 못했습니다</h3></div><strong>재시도 필요</strong></div><p>제출 자료는 기존 평가에 아직 반영되지 않았습니다.</p>{error && <div className="supplemental-assessment__error" role="alert"><p>{error.message}</p></div>}<button className="button button--primary" type="button" disabled={phase === 'running'} onClick={() => void request(true)}>{phase === 'running' ? '다시 평가하는 중…' : '보완평가 다시 시도'}</button></section>

  const uncertainty = assessment.uncertainty
  return <section className={`supplemental-assessment supplemental-assessment--${assessment.status.toLowerCase()}`} aria-labelledby="supplemental-title">
    <div className="supplemental-assessment__heading"><div><span>보완평가</span><h3 id="supplemental-title">{assessment.status === 'COMPLETED' ? '보완평가를 완료했습니다' : '보완평가 결과를 확인해주세요'}</h3></div></div>
    <p>{assessment.status === 'COMPLETED' ? '품질을 확인한 자료를 반영한 결과입니다. 기존 평가와 나란히 비교할 수 있습니다.' : '현재 보완평가를 완료하지 못했습니다.'}</p>
    {uncertainty && <div className="supplemental-assessment__result"><div><span>현재 확인 가능한 평가 범위</span><strong>{uncertainty.gradeSet.length > 0 ? assessmentGradeSetLabel(uncertainty.gradeSet) : '확인 가능한 평가 구간이 없습니다.'}</strong></div>{(uncertainty.pointEstimate !== null || uncertainty.lowerBound !== null || uncertainty.upperBound !== null) && <dl>{uncertainty.pointEstimate !== null && <div><dt>모델 추정값</dt><dd>{uncertainty.pointEstimate}</dd></div>}{(uncertainty.lowerBound !== null || uncertainty.upperBound !== null) && <div><dt>수치 범위</dt><dd>{uncertainty.lowerBound !== null && uncertainty.upperBound !== null ? `${uncertainty.lowerBound} ~ ${uncertainty.upperBound}` : uncertainty.lowerBound ?? uncertainty.upperBound}</dd></div>}</dl>}</div>}
    <CustomerTechnicalDetails><dl><div><dt>처리 상태</dt><dd><code>{assessment.status}</code></dd></div><div><dt>상태 코드</dt><dd><code>{assessment.reasonCode ?? '없음'}</code></dd></div><div><dt>반영 자료</dt><dd>{assessment.acceptedEvidenceCount}건</dd></div><div><dt>계산 시점</dt><dd>{formatDate(assessment.calculatedAt)}</dd></div><div><dt>기준평가 ID</dt><dd><code>{assessment.baselineAssessmentId}</code></dd></div><div><dt>보완평가 ID</dt><dd><code>{assessment.supplementalAssessmentId}</code></dd></div><div><dt>입력 데이터 묶음</dt><dd><code>{assessment.inputSnapshotId}</code></dd></div><div><dt>모델 버전</dt><dd><code>{assessment.modelVersion ?? '제공되지 않음'}</code></dd></div>{uncertainty && <><div><dt>보정 방식</dt><dd><code>{uncertainty.calibrationMode}</code></dd></div><div><dt>보정 버전</dt><dd><code>{uncertainty.calibrationVersion}</code></dd></div></>}</dl></CustomerTechnicalDetails>
    {assessment.status === 'COMPLETED' && <AssessmentComparisonPanel sessionId={sessionId} baselineAssessmentId={assessment.baselineAssessmentId} supplementalAssessmentId={assessment.supplementalAssessmentId} qualityCheckId={assessment.qualityCheckId} />}
  </section>
}

export default SupplementalAssessmentPanel
