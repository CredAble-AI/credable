import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { normalizeAssessmentReviewError } from '../api/assessmentReviewClient'
import { assessmentReviewProvider } from '../hooks/useAssessmentReviewState'
import type { ApiError } from '../types/api'
import type { AssessmentReviewProcessingStatus, AssessmentReviewRequestResponse, CustomerAssessmentReviewReason } from '../types/assessmentReview'
import CustomerTechnicalDetails from './CustomerTechnicalDetails'
import './AssessmentReviewPanel.css'

interface AssessmentReviewPanelProps { sessionId: string }
type Phase = 'loading' | 'requesting' | 'idle'

const statusCopy: Record<AssessmentReviewProcessingStatus, { title: string; description: string }> = {
  PENDING: { title: '평가 결과 재확인 요청이 접수됐습니다', description: '요청이 대기열에 등록됐습니다. 담당자가 확인하기 전까지 현재 평가 결과가 유지됩니다.' },
  IN_REVIEW: { title: '담당자가 평가 결과를 확인하고 있습니다', description: '담당자가 검토를 시작했습니다. 결과가 확정될 때까지 현재 평가 결과가 유지됩니다.' },
  COMPLETED: { title: '재확인 처리가 완료됐습니다', description: '담당자의 처리 결과가 기록됐습니다.' },
}
const targetLabels = { BASELINE_ASSESSMENT: '기준평가', SUPPLEMENTAL_ASSESSMENT: '보완평가' } as const
const reasonOptions: { code: CustomerAssessmentReviewReason; label: string; description: string }[] = [
  { code: 'INCORRECT_INFORMATION', label: '평가에 사용된 정보가 실제와 다릅니다', description: '금액, 기간, 사업 정보 등 확인된 내용이 사실과 다른 경우입니다.' },
  { code: 'MISSING_RECENT_INFORMATION', label: '최근 정보가 반영되지 않았습니다', description: '최근의 매출이나 거래가 평가 기준시점 이후라 반영되지 않은 경우입니다.' },
  { code: 'EXCLUDED_EVIDENCE_DISPUTED', label: '제출한 자료가 제외된 사유를 확인하고 싶습니다', description: '제출한 자료가 평가에 사용되지 않은 이유를 다시 확인받고 싶은 경우입니다.' },
]
const reasonLabels = Object.fromEntries(reasonOptions.map((item) => [item.code, item.label])) as Record<CustomerAssessmentReviewReason, string>
const formatDate = (value: string | null) => value ? new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) : '확인되지 않음'

function AssessmentReviewPanel({ sessionId }: AssessmentReviewPanelProps) {
  const [result, setResult] = useState<AssessmentReviewRequestResponse | null>(null)
  const [reasonCode, setReasonCode] = useState<CustomerAssessmentReviewReason | null>(null)
  const [phase, setPhase] = useState<Phase>('loading')
  const [error, setError] = useState<ApiError | null>(null)
  const controllerRef = useRef<AbortController | null>(null)
  const sequenceRef = useRef(0)

  const acceptResponse = useCallback((response: AssessmentReviewRequestResponse, required: boolean) => {
    if (response.sessionId !== sessionId || (response.reviewRequest && response.reviewRequest.demoOnly !== true)) throw { code: 'ASSESSMENT_REVIEW_CONTEXT_MISMATCH', message: '현재 세션의 평가 재확인 요청을 확인할 수 없습니다.', retryable: true } satisfies ApiError
    if (required && !response.reviewRequest) throw { code: 'ASSESSMENT_REVIEW_RESULT_MISSING', message: '서버가 평가 재확인 요청 결과를 반환하지 않았습니다.', retryable: true } satisfies ApiError
    if (response.reviewRequest && !response.underwriterReviewId) throw { code: 'ASSESSMENT_REVIEW_CONTEXT_MISMATCH', message: '현재 요청과 연결된 심사역 검토 화면을 확인할 수 없습니다.', retryable: true } satisfies ApiError
    return response
  }, [sessionId])

  const send = useCallback(async (create: CustomerAssessmentReviewReason | null) => {
    controllerRef.current?.abort()
    const controller = new AbortController(); controllerRef.current = controller
    const sequence = ++sequenceRef.current
    setPhase(create ? 'requesting' : 'loading'); setError(null)
    try {
      const response = create
        ? await assessmentReviewProvider.request(sessionId, create, controller.signal)
        : await assessmentReviewProvider.get(sessionId, controller.signal)
      const accepted = acceptResponse(response, create !== null)
      if (sequence === sequenceRef.current) setResult(accepted)
    } catch (caught) {
      if (!controller.signal.aborted && sequence === sequenceRef.current) setError(normalizeAssessmentReviewError(caught))
    } finally {
      if (sequence === sequenceRef.current) setPhase('idle')
    }
  }, [acceptResponse, sessionId])

  useEffect(() => {
    queueMicrotask(() => void send(null))
    return () => { sequenceRef.current += 1; controllerRef.current?.abort() }
  }, [send])

  if (phase === 'loading' && !result) return <section className="assessment-review assessment-review--loading" aria-label="평가 결과 재확인 요청 상태 확인"><span /><span /></section>

  const review = result?.reviewRequest ?? null
  const processing = result?.processing ?? null
  if (!review) return <section className="assessment-review" aria-labelledby="assessment-review-title">
    <div className="assessment-review__heading"><div><span>평가 결과 재확인</span><h3 id="assessment-review-title">담당자에게 재확인을 요청할 수 있습니다</h3></div><strong>요청 전</strong></div>
    <p>완료된 평가 결과를 담당자가 다시 확인하도록 요청합니다. 요청만으로 평가 결과가 변경되지는 않으며, 더 유리한 결과를 찾기 위한 기능이 아닙니다.</p>
    <fieldset className="assessment-review__reasons">
      <legend>어떤 점을 다시 확인해야 하나요?</legend>
      <p>선택한 사유와 관련된 정보만 확인합니다.</p>
      {reasonOptions.map((option) => (
        <label className={`assessment-review__reason${reasonCode === option.code ? ' assessment-review__reason--selected' : ''}`} key={option.code}>
          <input type="radio" name="customer-review-reason" value={option.code} checked={reasonCode === option.code} onChange={() => setReasonCode(option.code)} />
          <span><strong>{option.label}</strong><small>{option.description}</small></span>
        </label>
      ))}
    </fieldset>
    {error && <div className="assessment-review__error" role="alert"><p>{error.message}</p><small>{error.code}{error.requestId ? ` · 요청 ID ${error.requestId}` : ''}</small></div>}
    {error ? error.retryable && <button className="button button--secondary" type="button" onClick={() => void send(null)}>요청 상태 다시 확인</button> : <button className="button button--primary" type="button" disabled={phase !== 'idle' || !reasonCode} onClick={() => { if (reasonCode) void send(reasonCode) }}>{phase === 'requesting' ? '재확인 요청 중…' : '평가 결과 재확인 요청'}</button>}
  </section>

  const underwriterReviewId = result!.underwriterReviewId!
  const copy = processing ? statusCopy[processing.status] : { title: '평가 결과 재확인 요청이 저장됐습니다', description: '처리 상태는 서버 응답에서 확인되지 않았습니다.' }
  return <><section className={`assessment-review assessment-review--${processing?.status.toLowerCase() ?? 'unknown'}`} aria-labelledby="assessment-review-title">
    <div className="assessment-review__heading"><div><span>평가 결과 재확인</span><h3 id="assessment-review-title">{copy.title}</h3></div></div>
    <p>{copy.description}</p>
    {error && <div className="assessment-review__error" role="alert"><p>{error.message}</p><small>{error.code}{error.requestId ? ` · 요청 ID ${error.requestId}` : ''}</small></div>}
    <dl className="assessment-review__metadata"><div><dt>요청 사유</dt><dd>{review.customerReasonCode ? reasonLabels[review.customerReasonCode] : '기록되지 않음'}</dd></div><div><dt>검토 대상</dt><dd>{targetLabels[review.targetType]}</dd></div><div><dt>요청 시점</dt><dd>{formatDate(review.requestedAt)}</dd></div><div><dt>검토 시작</dt><dd>{formatDate(processing?.startedAt ?? null)}</dd></div><div><dt>검토 완료</dt><dd>{formatDate(processing?.completedAt ?? null)}</dd></div></dl>
    <CustomerTechnicalDetails><dl><div><dt>처리 상태</dt><dd><code>{processing?.status ?? '확인되지 않음'}</code></dd></div><div><dt>대상 평가 ID</dt><dd><code>{review.targetAssessmentId}</code></dd></div><div><dt>처리 결과 코드</dt><dd><code>{processing?.resultCode ?? '처리 중'}</code></dd></div><div><dt>모델 버전</dt><dd><code>{review.modelVersion}</code></dd></div><div><dt>요청 정책 버전</dt><dd><code>{review.requestPolicyVersion}</code></dd></div></dl></CustomerTechnicalDetails>
    <div className="assessment-review__actions"><button className="button button--secondary" type="button" disabled={phase !== 'idle'} onClick={() => void send(null)}>{phase === 'loading' ? '처리 상태 확인 중…' : '처리 상태 다시 확인'}</button><Link className="button button--primary" to={`/admin/reviews/${encodeURIComponent(underwriterReviewId)}`}>담당자 검토 화면 보기</Link></div>
    <p className="assessment-review__demo-note">시연 편의를 위해 고객 화면과 심사역 화면을 연결했습니다. 실제 운영 환경에서는 권한이 분리된 별도 심사역 시스템에서만 접근합니다.</p>
  </section><aside className="demo-underwriter-switcher" aria-label="시연 화면 전환"><div><span>시연 다음 단계</span><strong>고객 요청이 담당자 대기열에 등록됐습니다</strong></div><Link to={`/admin/reviews/${encodeURIComponent(underwriterReviewId)}`}>담당자 검토로 전환 <span aria-hidden="true">→</span></Link></aside></>
}

export default AssessmentReviewPanel
