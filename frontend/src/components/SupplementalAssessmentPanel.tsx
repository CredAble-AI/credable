import { useCallback, useEffect, useRef, useState } from 'react'
import { normalizeSupplementalAssessmentError } from '../api/supplementalAssessmentClient'
import { supplementalAssessmentProvider } from '../hooks/useSupplementalAssessmentState'
import type { ApiError } from '../types/api'
import type { SupplementalAssessmentResponse, SupplementalAssessmentState } from '../types/supplementalAssessment'

interface SupplementalAssessmentPanelProps { sessionId: string; submissionId: string; qualityCheckId: string }
type Phase = 'loading' | 'running' | 'idle'

const formatDate = (value: string) => new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
const displayNumber = (value: number | null) => value === null ? '제공되지 않음' : String(value)

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
      const response = run
        ? await supplementalAssessmentProvider.run(sessionId, submissionId, controller.signal)
        : await supplementalAssessmentProvider.get(sessionId, controller.signal)
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

  if (phase === 'loading' && !assessment) return <section className="supplemental-assessment supplemental-assessment--loading" aria-label="보완평가 상태 확인"><span /><span /></section>

  if (!assessment) return <section className="supplemental-assessment" aria-labelledby="supplemental-title"><div className="supplemental-assessment__heading"><div><span>SUPPLEMENTAL ASSESSMENT</span><h3 id="supplemental-title">검증된 증빙으로 다시 확인합니다</h3></div><strong>실행 전</strong></div><p>기준평가는 보존하고 서버가 현재 제출과 품질검증에 연결된 별도 보완평가를 생성합니다. 버튼을 누르기 전에는 자동으로 실행하지 않습니다.</p>{error && <div className="supplemental-assessment__error" role="alert"><p>{error.message}</p><small>{error.code}{error.requestId ? ` · 요청 ID ${error.requestId}` : ''}</small></div>}<button className="button button--primary" type="button" disabled={phase === 'running'} onClick={() => void request(true)}>{phase === 'running' ? '백엔드에서 재확인 중…' : '보완평가 실행'}</button></section>

  const uncertainty = assessment.uncertainty
  return <section className={`supplemental-assessment supplemental-assessment--${assessment.status.toLowerCase()}`} aria-labelledby="supplemental-title">
    <div className="supplemental-assessment__heading"><div><span>SUPPLEMENTAL ASSESSMENT</span><h3 id="supplemental-title">{assessment.status === 'COMPLETED' ? '보완평가를 완료했습니다' : '보완평가 결과를 확인해주세요'}</h3></div><strong>{assessment.status}</strong></div>
    <p>{assessment.status === 'COMPLETED' ? '백엔드가 검증된 Evidence를 반영한 별도 평가 결과를 반환했습니다.' : `서버 상태 코드 ${assessment.reasonCode ?? 'UNKNOWN'}`}</p>
    {uncertainty && <div className="supplemental-assessment__result"><div><span>가능한 Demo 평가 범위</span><strong>{uncertainty.gradeSet.length > 0 ? uncertainty.gradeSet.join(' · ') : '서버가 등급 범위를 제공하지 않음'}</strong></div><dl><div><dt>모델 추정값</dt><dd>{displayNumber(uncertainty.pointEstimate)}</dd></div><div><dt>수치 범위</dt><dd>{uncertainty.lowerBound === null || uncertainty.upperBound === null ? '제공되지 않음' : `${uncertainty.lowerBound} ~ ${uncertainty.upperBound}`}</dd></div><div><dt>보정 방식</dt><dd>{uncertainty.calibrationMode}</dd></div><div><dt>보정 버전</dt><dd><code>{uncertainty.calibrationVersion}</code></dd></div></dl></div>}
    <dl className="supplemental-assessment__metadata"><div><dt>반영 Evidence</dt><dd>{assessment.acceptedEvidenceCount}건</dd></div><div><dt>계산 시점</dt><dd>{formatDate(assessment.calculatedAt)}</dd></div><div><dt>기준평가 ID</dt><dd><code>{assessment.baselineAssessmentId}</code></dd></div><div><dt>보완평가 ID</dt><dd><code>{assessment.supplementalAssessmentId}</code></dd></div><div><dt>입력 Snapshot</dt><dd><code>{assessment.inputSnapshotId}</code></dd></div><div><dt>모델 버전</dt><dd><code>{assessment.modelVersion ?? '제공되지 않음'}</code></dd></div></dl>
  </section>
}

export default SupplementalAssessmentPanel
