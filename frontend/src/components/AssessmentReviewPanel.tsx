import { useCallback, useEffect, useRef, useState } from 'react'
import { normalizeAssessmentReviewError } from '../api/assessmentReviewClient'
import { assessmentReviewProvider } from '../hooks/useAssessmentReviewState'
import type { ApiError } from '../types/api'
import type { AssessmentReviewProcessingStatus, AssessmentReviewRequestResponse } from '../types/assessmentReview'
import './AssessmentReviewPanel.css'

interface AssessmentReviewPanelProps { sessionId: string }
type Phase = 'loading' | 'requesting' | 'idle'

const statusCopy: Record<AssessmentReviewProcessingStatus, { title: string; description: string }> = {
  PENDING: { title: '평가 결과 재확인 요청이 접수됐습니다', description: '요청이 대기열에 등록됐습니다. 기존 평가 결과는 심사역 처리 전까지 그대로 유지됩니다.' },
  IN_REVIEW: { title: '심사역이 평가 결과를 확인하고 있습니다', description: '서버가 심사역 검토 시작 상태를 반환했습니다. 처리 결과가 확정될 때까지 기존 평가 결과를 유지합니다.' },
  COMPLETED: { title: '처리 결과가 기록되었습니다', description: '서버가 심사역 처리 결과 코드를 반환했습니다. 프론트엔드는 결과의 의미를 다시 판단하지 않습니다.' },
}
const targetLabels = { BASELINE_ASSESSMENT: '기준평가', SUPPLEMENTAL_ASSESSMENT: '보완평가' } as const
const formatDate = (value: string | null) => value ? new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) : '확인되지 않음'

function AssessmentReviewPanel({ sessionId }: AssessmentReviewPanelProps) {
  const [result, setResult] = useState<AssessmentReviewRequestResponse | null>(null)
  const [phase, setPhase] = useState<Phase>('loading')
  const [error, setError] = useState<ApiError | null>(null)
  const controllerRef = useRef<AbortController | null>(null)
  const sequenceRef = useRef(0)

  const acceptResponse = useCallback((response: AssessmentReviewRequestResponse, required: boolean) => {
    if (response.sessionId !== sessionId || (response.reviewRequest && response.reviewRequest.demoOnly !== true)) throw { code: 'ASSESSMENT_REVIEW_CONTEXT_MISMATCH', message: '현재 세션의 평가 재확인 요청을 확인할 수 없습니다.', retryable: true } satisfies ApiError
    if (required && !response.reviewRequest) throw { code: 'ASSESSMENT_REVIEW_RESULT_MISSING', message: '서버가 평가 재확인 요청 결과를 반환하지 않았습니다.', retryable: true } satisfies ApiError
    return response
  }, [sessionId])

  const send = useCallback(async (create: boolean) => {
    controllerRef.current?.abort()
    const controller = new AbortController(); controllerRef.current = controller
    const sequence = ++sequenceRef.current
    setPhase(create ? 'requesting' : 'loading'); setError(null)
    try {
      const response = create
        ? await assessmentReviewProvider.request(sessionId, controller.signal)
        : await assessmentReviewProvider.get(sessionId, controller.signal)
      const accepted = acceptResponse(response, create)
      if (sequence === sequenceRef.current) setResult(accepted)
    } catch (caught) {
      if (!controller.signal.aborted && sequence === sequenceRef.current) setError(normalizeAssessmentReviewError(caught))
    } finally {
      if (sequence === sequenceRef.current) setPhase('idle')
    }
  }, [acceptResponse, sessionId])

  useEffect(() => {
    queueMicrotask(() => void send(false))
    return () => { sequenceRef.current += 1; controllerRef.current?.abort() }
  }, [send])

  if (phase === 'loading' && !result) return <section className="assessment-review assessment-review--loading" aria-label="평가 결과 재확인 요청 상태 확인"><span /><span /></section>

  const review = result?.reviewRequest ?? null
  const processing = result?.processing ?? null
  if (!review) return <section className="assessment-review" aria-labelledby="assessment-review-title">
    <div className="assessment-review__heading"><div><span>CUSTOMER REVIEW REQUEST</span><h3 id="assessment-review-title">평가 결과 재확인을 요청할 수 있습니다</h3></div><strong>요청 전</strong></div>
    <p>완료된 평가 결과를 심사역이 다시 확인하도록 요청합니다. 대상 평가는 백엔드가 현재 평가 이력에 따라 확정하며 요청만으로 평가 결과가 변경되지는 않습니다.</p>
    {error && <div className="assessment-review__error" role="alert"><p>{error.message}</p><small>{error.code}{error.requestId ? ` · 요청 ID ${error.requestId}` : ''}</small></div>}
    {error ? error.retryable && <button className="button button--secondary" type="button" onClick={() => void send(false)}>요청 상태 다시 확인</button> : <button className="button button--primary" type="button" disabled={phase !== 'idle'} onClick={() => void send(true)}>{phase === 'requesting' ? '재확인 요청 중…' : '평가 결과 재확인 요청'}</button>}
  </section>

  const copy = processing ? statusCopy[processing.status] : { title: '평가 결과 재확인 요청이 저장됐습니다', description: '처리 상태는 서버 응답에서 확인되지 않았습니다.' }
  return <section className={`assessment-review assessment-review--${processing?.status.toLowerCase() ?? 'unknown'}`} aria-labelledby="assessment-review-title">
    <div className="assessment-review__heading"><div><span>CUSTOMER REVIEW REQUEST</span><h3 id="assessment-review-title">{copy.title}</h3></div><strong>{processing?.status ?? 'STATUS_UNKNOWN'}</strong></div>
    <p>{copy.description}</p>
    {error && <div className="assessment-review__error" role="alert"><p>{error.message}</p><small>{error.code}{error.requestId ? ` · 요청 ID ${error.requestId}` : ''}</small></div>}
    <dl className="assessment-review__metadata"><div><dt>검토 대상</dt><dd>{targetLabels[review.targetType]}</dd></div><div><dt>대상 평가 ID</dt><dd><code>{review.targetAssessmentId}</code></dd></div><div><dt>처리 결과 코드</dt><dd><code>{processing?.resultCode ?? '처리 중'}</code></dd></div><div><dt>요청 시점</dt><dd>{formatDate(review.requestedAt)}</dd></div><div><dt>검토 시작</dt><dd>{formatDate(processing?.startedAt ?? null)}</dd></div><div><dt>검토 완료</dt><dd>{formatDate(processing?.completedAt ?? null)}</dd></div><div><dt>모델 버전</dt><dd><code>{review.modelVersion}</code></dd></div><div><dt>요청 정책 버전</dt><dd><code>{review.requestPolicyVersion}</code></dd></div></dl>
    <button className="button button--secondary" type="button" disabled={phase !== 'idle'} onClick={() => void send(false)}>{phase === 'loading' ? '처리 상태 확인 중…' : '처리 상태 다시 확인'}</button>
  </section>
}

export default AssessmentReviewPanel
