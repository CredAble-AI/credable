import { useCallback, useEffect, useRef, useState } from 'react'
import { normalizeAssessmentExplanationError } from '../api/assessmentExplanationClient'
import { assessmentExplanationProvider } from '../hooks/useAssessmentExplanationState'
import type { ApiError } from '../types/api'
import type { AssessmentExplanationResponse, AssessmentExplanationState, ExplanationRenderingMode, ExplanationTargetType } from '../types/assessmentExplanation'
import CustomerTechnicalDetails from './CustomerTechnicalDetails'
import './AssessmentExplanationPanel.css'

interface AssessmentExplanationPanelProps {
  sessionId: string
  /** Read-only viewers (the underwriter screen) never trigger generation. */
  readOnly?: boolean
}
type Phase = 'loading' | 'generating' | 'idle'
type RequestKind = 'load' | 'generate'

const renderingLabels: Record<ExplanationRenderingMode, string> = {
  DEMO_TEMPLATE: '구조화 결과 안내',
  GENERATIVE_AI: 'AI 기반 안내',
  RULE_FALLBACK: '기본 안내',
}
const targetLabels: Record<ExplanationTargetType, string> = {
  BASELINE_ASSESSMENT: '기존 평가',
  SUPPLEMENTAL_ASSESSMENT: '보완평가',
}
const formatDate = (value: string) => new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))

function AssessmentExplanationPanel({ sessionId, readOnly = false }: AssessmentExplanationPanelProps) {
  const [explanation, setExplanation] = useState<AssessmentExplanationState | null>(null)
  const [phase, setPhase] = useState<Phase>('loading')
  const [error, setError] = useState<ApiError | null>(null)
  const [failedRequest, setFailedRequest] = useState<RequestKind | null>(null)
  const controllerRef = useRef<AbortController | null>(null)
  const sequenceRef = useRef(0)

  const acceptResponse = useCallback((response: AssessmentExplanationResponse, required: boolean) => {
    if (response.sessionId !== sessionId || (response.explanation && response.explanation.demoOnly !== true)) throw {
      code: 'ASSESSMENT_EXPLANATION_CONTEXT_MISMATCH', message: '현재 세션의 평가 결과 설명을 확인할 수 없습니다.', retryable: true,
    } satisfies ApiError
    if (required && !response.explanation) throw {
      code: 'ASSESSMENT_EXPLANATION_RESULT_MISSING', message: '서버가 평가 결과 설명을 반환하지 않았습니다.', retryable: true,
    } satisfies ApiError
    return response.explanation
  }, [sessionId])

  const send = useCallback(async (kind: RequestKind) => {
    controllerRef.current?.abort()
    const controller = new AbortController(); controllerRef.current = controller
    const sequence = ++sequenceRef.current
    setPhase(kind === 'generate' ? 'generating' : 'loading'); setError(null); setFailedRequest(null)
    try {
      let response = kind === 'generate'
        ? await assessmentExplanationProvider.generate(sessionId, controller.signal)
        : await assessmentExplanationProvider.get(sessionId, controller.signal)
      if (kind === 'load' && !readOnly && !acceptResponse(response, false)) {
        if (sequence === sequenceRef.current) setPhase('generating')
        response = await assessmentExplanationProvider.generate(sessionId, controller.signal)
        kind = 'generate'
      }
      const accepted = acceptResponse(response, kind === 'generate')
      if (sequence === sequenceRef.current) setExplanation(accepted)
    } catch (caught) {
      if (!controller.signal.aborted && sequence === sequenceRef.current) {
        setError(normalizeAssessmentExplanationError(caught)); setFailedRequest(kind)
      }
    } finally {
      if (sequence === sequenceRef.current) setPhase('idle')
    }
  }, [acceptResponse, readOnly, sessionId])

  useEffect(() => {
    queueMicrotask(() => void send('load'))
    return () => { sequenceRef.current += 1; controllerRef.current?.abort() }
  }, [send])

  if (phase !== 'idle' && !explanation) return <section className="assessment-explanation assessment-explanation--loading" aria-label="평가 결과 안내 준비 중"><span /><span /><p>확정된 결과와 다음 단계를 알기 쉽게 정리하고 있습니다.</p></section>

  if (!explanation) return <section className="assessment-explanation" aria-labelledby="assessment-explanation-title">
    <div className="assessment-explanation__heading"><div><span>평가 결과 안내</span><h3 id="assessment-explanation-title">결과 안내를 준비하지 못했습니다</h3></div><strong>재시도 필요</strong></div>
    <p>평가 결과는 변경되지 않았습니다. 결과와 다음 단계 설명만 다시 준비합니다.</p>
    {error && <div className="assessment-explanation__error" role="alert"><p>{error.message}</p><CustomerTechnicalDetails title="오류 기술 정보 보기"><dl><div><dt>오류 코드</dt><dd><code>{error.code}</code></dd></div>{error.requestId && <div><dt>요청 ID</dt><dd><code>{error.requestId}</code></dd></div>}</dl></CustomerTechnicalDetails></div>}
    <button className="button button--secondary" type="button" disabled={phase !== 'idle'} onClick={() => void send(readOnly || failedRequest === 'load' ? 'load' : 'generate')}>{phase === 'generating' ? '안내를 준비하는 중…' : '결과 안내 다시 준비'}</button>
  </section>

  return <section className={`assessment-explanation assessment-explanation--${explanation.renderingMode.toLowerCase()}`} aria-labelledby="assessment-explanation-title">
    <div className="assessment-explanation__heading"><div><span>평가 결과 안내</span><h3 id="assessment-explanation-title">{explanation.headline}</h3></div><strong>{renderingLabels[explanation.renderingMode]}</strong></div>
    {explanation.fallbackApplied && <div className="assessment-explanation__fallback" role="status">AI 설명을 불러오지 못해 동일한 평가 결과를 기본 안내 문구로 보여드립니다.</div>}
    <div className="assessment-explanation__sections">{explanation.sections.map((section, index) => <article key={section.messageCode}><span>{String(index + 1).padStart(2, '0')}</span><h4>{section.title}</h4><p>{section.text}</p></article>)}</div>
    <p className="assessment-explanation__caution">{explanation.cautionText}</p>
    {error && <div className="assessment-explanation__error" role="alert"><p>{error.message}</p></div>}
    <CustomerTechnicalDetails><dl><div><dt>설명 방식</dt><dd><code>{explanation.renderingMode}</code></dd></div>{explanation.fallbackApplied && <div><dt>대체 안내 사유</dt><dd><code>{explanation.fallbackReasonCode}</code></dd></div>}<div><dt>설명 대상</dt><dd>{targetLabels[explanation.targetType]}</dd></div><div><dt>대상 평가 ID</dt><dd><code>{explanation.targetAssessmentId}</code></dd></div><div><dt>생성 시점</dt><dd>{formatDate(explanation.generatedAt)}</dd></div><div><dt>설명 정책</dt><dd><code>{explanation.explanationPolicyVersion}</code></dd></div><div><dt>설명 제공 방식</dt><dd><code>{explanation.providerVersion}</code></dd></div><div><dt>모델 버전</dt><dd><code>{explanation.modelVersion ?? '사용하지 않음'}</code></dd></div></dl><div className="assessment-explanation__sources"><span>근거 식별자</span>{explanation.sourceReferences.map((source) => <code key={source.sourceId}>{source.sourceType} · {source.sourceId}</code>)}</div></CustomerTechnicalDetails>
    <button className="button button--secondary" type="button" disabled={phase !== 'idle'} onClick={() => void send('load')}>{phase === 'loading' ? '설명 상태 확인 중…' : '설명 새로고침'}</button>
  </section>
}

export default AssessmentExplanationPanel
