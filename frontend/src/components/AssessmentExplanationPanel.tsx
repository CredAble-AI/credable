import { useCallback, useEffect, useRef, useState } from 'react'
import { normalizeAssessmentExplanationError } from '../api/assessmentExplanationClient'
import { assessmentExplanationProvider } from '../hooks/useAssessmentExplanationState'
import type { ApiError } from '../types/api'
import type { AssessmentExplanationResponse, AssessmentExplanationState, ExplanationRenderingMode, ExplanationTargetType } from '../types/assessmentExplanation'
import './AssessmentExplanationPanel.css'

interface AssessmentExplanationPanelProps { sessionId: string }
type Phase = 'loading' | 'generating' | 'idle'
type RequestKind = 'load' | 'generate'

const renderingLabels: Record<ExplanationRenderingMode, string> = {
  DEMO_TEMPLATE: 'Demo 템플릿',
  GENERATIVE_AI: '통제형 AI 설명',
  RULE_FALLBACK: '규칙 기반 설명',
}
const targetLabels: Record<ExplanationTargetType, string> = {
  BASELINE_ASSESSMENT: '기준평가',
  SUPPLEMENTAL_ASSESSMENT: '보완평가',
}
const formatDate = (value: string) => new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))

function AssessmentExplanationPanel({ sessionId }: AssessmentExplanationPanelProps) {
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
      const response = kind === 'generate'
        ? await assessmentExplanationProvider.generate(sessionId, controller.signal)
        : await assessmentExplanationProvider.get(sessionId, controller.signal)
      const accepted = acceptResponse(response, kind === 'generate')
      if (sequence === sequenceRef.current) setExplanation(accepted)
    } catch (caught) {
      if (!controller.signal.aborted && sequence === sequenceRef.current) {
        setError(normalizeAssessmentExplanationError(caught)); setFailedRequest(kind)
      }
    } finally {
      if (sequence === sequenceRef.current) setPhase('idle')
    }
  }, [acceptResponse, sessionId])

  useEffect(() => {
    queueMicrotask(() => void send('load'))
    return () => { sequenceRef.current += 1; controllerRef.current?.abort() }
  }, [send])

  if (phase === 'loading' && !explanation) return <section className="assessment-explanation assessment-explanation--loading" aria-label="평가 결과 설명 상태 확인"><span /><span /></section>

  if (!explanation) return <section className="assessment-explanation" aria-labelledby="assessment-explanation-title">
    <div className="assessment-explanation__heading"><div><span>CONTROLLED EXPLANATION</span><h3 id="assessment-explanation-title">서버 결과를 쉽게 설명합니다</h3></div><strong>생성 전</strong></div>
    <p>서버가 확정한 평가·정책 결과만 근거로 사용합니다. 설명은 신용등급, 정책 경로 또는 금융조건을 만들거나 바꾸지 않습니다.</p>
    {error && <div className="assessment-explanation__error" role="alert"><p>{error.message}</p><small>{error.code}{error.requestId ? ` · 요청 ID ${error.requestId}` : ''}</small></div>}
    <button className={`button ${failedRequest === 'load' ? 'button--secondary' : 'button--primary'}`} type="button" disabled={phase !== 'idle'} onClick={() => void send(failedRequest === 'load' ? 'load' : 'generate')}>{failedRequest === 'load' ? '설명 상태 다시 확인' : phase === 'generating' ? '서버에서 설명 생성 중…' : '평가 결과 설명 생성'}</button>
  </section>

  return <section className={`assessment-explanation assessment-explanation--${explanation.renderingMode.toLowerCase()}`} aria-labelledby="assessment-explanation-title">
    <div className="assessment-explanation__heading"><div><span>CONTROLLED EXPLANATION</span><h3 id="assessment-explanation-title">{explanation.headline}</h3></div><strong>{renderingLabels[explanation.renderingMode]}</strong></div>
    {explanation.fallbackApplied && <div className="assessment-explanation__fallback" role="status">Provider 결과를 사용하지 않고 서버 규칙 설명으로 전환했습니다. <code>{explanation.fallbackReasonCode}</code></div>}
    <div className="assessment-explanation__sections">{explanation.sections.map((section) => <article key={section.messageCode}><span>{section.messageCode}</span><h4>{section.title}</h4><p>{section.text}</p></article>)}</div>
    <p className="assessment-explanation__caution">{explanation.cautionText}</p>
    {error && <div className="assessment-explanation__error" role="alert"><p>{error.message}</p><small>{error.code}{error.requestId ? ` · 요청 ID ${error.requestId}` : ''}</small></div>}
    <details className="assessment-explanation__metadata"><summary>설명 근거 및 버전 정보</summary><dl><div><dt>설명 대상</dt><dd>{targetLabels[explanation.targetType]}</dd></div><div><dt>대상 평가 ID</dt><dd><code>{explanation.targetAssessmentId}</code></dd></div><div><dt>생성 시점</dt><dd>{formatDate(explanation.generatedAt)}</dd></div><div><dt>설명 정책</dt><dd><code>{explanation.explanationPolicyVersion}</code></dd></div><div><dt>Provider</dt><dd><code>{explanation.providerVersion}</code></dd></div><div><dt>모델 버전</dt><dd><code>{explanation.modelVersion ?? '사용하지 않음'}</code></dd></div></dl><div className="assessment-explanation__sources"><span>서버 근거</span>{explanation.sourceReferences.map((source) => <code key={source.sourceId}>{source.sourceType} · {source.sourceId}</code>)}</div></details>
    <button className="button button--secondary" type="button" disabled={phase !== 'idle'} onClick={() => void send('load')}>{phase === 'loading' ? '설명 상태 확인 중…' : '최신 설명 상태 확인'}</button>
  </section>
}

export default AssessmentExplanationPanel
