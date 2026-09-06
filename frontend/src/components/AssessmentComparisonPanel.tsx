import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { normalizeAssessmentComparisonError } from '../api/assessmentComparisonClient'
import { assessmentComparisonProvider } from '../hooks/useAssessmentComparisonState'
import type { ApiError } from '../types/api'
import type { AssessmentUncertainty } from '../types/assessment'
import type { AssessmentComparisonContext, AssessmentComparisonResponse, AssessmentComparisonState, AssessmentUncertaintyChange } from '../types/assessmentComparison'
import { assessmentGradeSetLabel } from '../utils/assessmentDisplay'
import EvidenceResolutionPanel from './EvidenceResolutionPanel'
import CustomerTechnicalDetails from './CustomerTechnicalDetails'

interface AssessmentComparisonPanelProps extends AssessmentComparisonContext { sessionId: string }
type Phase = 'loading' | 'comparing' | 'idle'

const changeCopy: Record<AssessmentUncertaintyChange, { title: string; description: string }> = {
  NARROWED: { title: '가능한 결과 범위가 줄었습니다', description: '추가 자료를 반영한 뒤 가능한 결과 범위가 더 명확해졌습니다.' },
  UNCHANGED: { title: '가능한 결과 범위가 유지되었습니다', description: '추가 자료를 반영했지만 가능한 결과 범위는 동일합니다.' },
  EXPANDED: { title: '가능한 결과 범위가 넓어졌습니다', description: '추가 자료를 반영한 뒤 가능한 결과 범위가 넓어졌습니다.' },
  SHIFTED: { title: '가능한 결과 범위가 이동했습니다', description: '추가 자료를 반영한 뒤 가능한 결과 범위가 다른 구간으로 이동했습니다.' },
  NOT_COMPARABLE: { title: '같은 기준으로 비교할 수 없습니다', description: '두 평가의 기준 또는 결과 형태가 달라 직접 비교하지 않습니다.' },
}
const basisLabels = { GRADE_SET: '등급 집합', NUMERIC_INTERVAL: '수치 구간', NOT_COMPARABLE: '비교 불가' }
const formatDate = (value: string) => new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))

function UncertaintyCard({ label, uncertainty }: { label: string; uncertainty: AssessmentUncertainty | null }) {
  const result = uncertainty?.gradeSet.length ? assessmentGradeSetLabel(uncertainty.gradeSet) : uncertainty?.lowerBound !== null && uncertainty?.lowerBound !== undefined && uncertainty.upperBound !== null ? `${uncertainty.lowerBound} ~ ${uncertainty.upperBound}` : '비교 가능한 범위 없음'
  return <article className="assessment-comparison__card"><span>{label}</span><strong>{result}</strong></article>
}

function AssessmentComparisonPanel({ sessionId, baselineAssessmentId, supplementalAssessmentId, qualityCheckId }: AssessmentComparisonPanelProps) {
  const [comparison, setComparison] = useState<AssessmentComparisonState | null>(null)
  const [phase, setPhase] = useState<Phase>('loading')
  const [error, setError] = useState<ApiError | null>(null)
  const controllerRef = useRef<AbortController | null>(null)
  const sequenceRef = useRef(0)
  const context = useMemo(() => ({ baselineAssessmentId, supplementalAssessmentId, qualityCheckId }), [baselineAssessmentId, qualityCheckId, supplementalAssessmentId])

  const acceptResponse = useCallback((response: AssessmentComparisonResponse, required: boolean) => {
    if (response.sessionId !== sessionId) throw { code: 'ASSESSMENT_COMPARISON_CONTEXT_MISMATCH', message: '현재 세션의 평가 비교 상태를 확인할 수 없습니다.', retryable: true } satisfies ApiError
    const result = response.comparison
    if (!result) {
      if (required) throw { code: 'ASSESSMENT_COMPARISON_RESULT_MISSING', message: '서버가 평가 비교 결과를 반환하지 않았습니다.', retryable: true } satisfies ApiError
      return null
    }
    const matchesLineage = result.baselineAssessmentId === baselineAssessmentId && result.supplementalAssessmentId === supplementalAssessmentId && result.qualityCheckId === qualityCheckId
    if (!matchesLineage) {
      if (required) throw { code: 'ASSESSMENT_COMPARISON_CONTEXT_MISMATCH', message: '현재 평가 이력과 일치하는 비교 결과를 확인할 수 없습니다.', retryable: true } satisfies ApiError
      return null
    }
    return result
  }, [baselineAssessmentId, qualityCheckId, sessionId, supplementalAssessmentId])

  const request = useCallback(async (compare: boolean) => {
    controllerRef.current?.abort()
    const controller = new AbortController(); controllerRef.current = controller
    const sequence = ++sequenceRef.current
    setPhase(compare ? 'comparing' : 'loading'); setError(null)
    try {
      let response = compare
        ? await assessmentComparisonProvider.compare(sessionId, context, controller.signal)
        : await assessmentComparisonProvider.get(sessionId, controller.signal)
      if (!compare && !acceptResponse(response, false)) {
        if (sequence === sequenceRef.current) setPhase('comparing')
        response = await assessmentComparisonProvider.compare(sessionId, context, controller.signal)
        compare = true
      }
      const result = acceptResponse(response, compare)
      if (sequence === sequenceRef.current) setComparison(result)
    } catch (caught) {
      if (!controller.signal.aborted && sequence === sequenceRef.current) setError(normalizeAssessmentComparisonError(caught))
    } finally {
      if (sequence === sequenceRef.current) setPhase('idle')
    }
  }, [acceptResponse, context, sessionId])

  useEffect(() => {
    queueMicrotask(() => void request(false))
    return () => { sequenceRef.current += 1; controllerRef.current?.abort() }
  }, [request])

  if (phase !== 'idle' && !comparison) return <section className="assessment-comparison assessment-comparison--loading" aria-label="평가 전후 비교 중"><span /><span /><p>추가 자료 반영 전·후의 결과 범위를 비교하고 있습니다.</p></section>

  if (!comparison) return <section className="assessment-comparison" aria-labelledby="comparison-title"><div className="assessment-comparison__heading"><div><span>평가 전후 비교</span><h4 id="comparison-title">결과 변화를 확인하지 못했습니다</h4></div><strong>재시도 필요</strong></div><p>기존 평가와 보완평가 결과는 그대로 보존됩니다.</p>{error && <div className="assessment-comparison__error" role="alert"><p>{error.message}</p></div>}<button className="button button--secondary" type="button" disabled={phase === 'comparing'} onClick={() => void request(true)}>{phase === 'comparing' ? '비교하는 중…' : '결과 비교 다시 시도'}</button></section>

  const copy = changeCopy[comparison.uncertaintyChange]
  return <section className={`assessment-comparison assessment-comparison--${comparison.uncertaintyChange.toLowerCase()}`} aria-labelledby="comparison-title">
    <div className="assessment-comparison__heading"><div><span>평가 전후 비교</span><h4 id="comparison-title">{copy.title}</h4></div></div>
    <p>{copy.description}</p>
    <div className="assessment-comparison__notice">이는 신용도 개선, 승인 가능성 상승 또는 대출 조건 확정을 의미하지 않습니다.</div>
    <div className="assessment-comparison__cards"><UncertaintyCard label="기존 평가" uncertainty={comparison.beforeUncertainty} /><UncertaintyCard label="보완평가" uncertainty={comparison.afterUncertainty} /></div>
    <CustomerTechnicalDetails><dl><div><dt>변화 상태</dt><dd><code>{comparison.uncertaintyChange}</code></dd></div><div><dt>비교 기준</dt><dd>{basisLabels[comparison.basis]}</dd></div><div><dt>비교 시점</dt><dd>{formatDate(comparison.comparedAt)}</dd></div><div><dt>비교 ID</dt><dd><code>{comparison.comparisonId}</code></dd></div><div><dt>기준평가 모델</dt><dd><code>{comparison.baselineModelVersion ?? '제공되지 않음'}</code></dd></div><div><dt>보완평가 모델</dt><dd><code>{comparison.supplementalModelVersion ?? '제공되지 않음'}</code></dd></div>{comparison.beforeUncertainty && <><div><dt>이전 보정 방식</dt><dd><code>{comparison.beforeUncertainty.calibrationMode}</code></dd></div><div><dt>이전 보정 버전</dt><dd><code>{comparison.beforeUncertainty.calibrationVersion}</code></dd></div></>}{comparison.afterUncertainty && <><div><dt>이후 보정 방식</dt><dd><code>{comparison.afterUncertainty.calibrationMode}</code></dd></div><div><dt>이후 보정 버전</dt><dd><code>{comparison.afterUncertainty.calibrationVersion}</code></dd></div></>}{comparison.rationaleCodes.map((code) => <div key={code}><dt>비교 근거 코드</dt><dd><code>{code}</code></dd></div>)}</dl></CustomerTechnicalDetails>
    <EvidenceResolutionPanel sessionId={sessionId} comparisonId={comparison.comparisonId} supplementalAssessmentId={comparison.supplementalAssessmentId} />
  </section>
}

export default AssessmentComparisonPanel
