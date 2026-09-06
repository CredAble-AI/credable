import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { normalizeAdminReviewError } from '../api/adminReviewClient'
import { adminReviewProvider } from '../hooks/useAdminReviewState'
import type { ApiError } from '../types/api'
import type { AdminReviewQueueItem, AdminReviewResultCode, AdminReviewStatus, AdminReviewTriggerType } from '../types/adminReview'
import './AdminReviewDetailPage.css'

const statusLabels: Record<AdminReviewStatus, string> = { PENDING: '접수 대기', IN_REVIEW: '검토 중', COMPLETED: '처리 완료' }
const triggerLabels: Record<AdminReviewTriggerType, string> = {
  EVIDENCE_QUALITY: 'Evidence 품질검토',
  CUSTOMER_ASSESSMENT_REVIEW: '고객 평가 재확인',
  POLICY_BOUNDARY: '정책 경계 검토',
  EVIDENCE_SELECTION: '최소 증빙 선택 검토',
  EVIDENCE_RESOLUTION: '증빙 수집 종료 검토',
}
const targetLabels = { BASELINE_ASSESSMENT: '기준평가', SUPPLEMENTAL_ASSESSMENT: '보완평가' } as const
const resultLabels: Record<AdminReviewResultCode, string> = {
  EVIDENCE_CONFIRMED: 'Evidence 확인',
  EVIDENCE_EXCLUDED: 'Evidence 제외',
  ASSESSMENT_CONFIRMED: '평가 확인',
  CORRECTION_REQUIRED: '정정 필요',
  ADDITIONAL_INFORMATION_REQUIRED: '추가 정보 필요',
  ESCALATED: '상위 검토 필요',
}
const allowedResults: Record<AdminReviewTriggerType, AdminReviewResultCode[]> = {
  EVIDENCE_QUALITY: ['EVIDENCE_CONFIRMED', 'EVIDENCE_EXCLUDED', 'ADDITIONAL_INFORMATION_REQUIRED', 'ESCALATED'],
  CUSTOMER_ASSESSMENT_REVIEW: ['ASSESSMENT_CONFIRMED', 'CORRECTION_REQUIRED', 'ADDITIONAL_INFORMATION_REQUIRED', 'ESCALATED'],
  POLICY_BOUNDARY: ['ASSESSMENT_CONFIRMED', 'CORRECTION_REQUIRED', 'ADDITIONAL_INFORMATION_REQUIRED', 'ESCALATED'],
  EVIDENCE_SELECTION: ['ASSESSMENT_CONFIRMED', 'CORRECTION_REQUIRED', 'ADDITIONAL_INFORMATION_REQUIRED', 'ESCALATED'],
  EVIDENCE_RESOLUTION: ['ASSESSMENT_CONFIRMED', 'CORRECTION_REQUIRED', 'ADDITIONAL_INFORMATION_REQUIRED', 'ESCALATED'],
}
const formatDate = (value?: string) => value ? new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) : '기록 없음'

function ReviewFacts({ review }: { review: AdminReviewQueueItem }) {
  return <section className="admin-detail-card" aria-labelledby="review-facts-title"><div className="admin-detail-card__heading"><div><p>{triggerLabels[review.triggerType]}</p><h2 id="review-facts-title">검토 요청 정보</h2></div><strong className={`admin-status admin-status--${review.status.toLowerCase()}`}>{statusLabels[review.status]}</strong></div><dl>
    <div><dt>검토 ID</dt><dd><code>{review.reviewId}</code></dd></div><div><dt>세션 ID</dt><dd><code>{review.sessionId}</code><Link className="admin-session-audit-link" to={`/admin/sessions/${encodeURIComponent(review.sessionId)}/audit`}>세션 처리 이력 보기</Link><Link className="admin-session-audit-link" to={`/admin/sessions/${encodeURIComponent(review.sessionId)}/evidence-burden`}>Evidence 부담 지표 보기</Link></dd></div><div><dt>Trigger</dt><dd><code>{review.triggerType}</code></dd></div><div><dt>Trigger ID</dt><dd><code>{review.triggerId}</code></dd></div>
    {review.evidenceType && <div><dt>Evidence 유형</dt><dd><code>{review.evidenceType}</code></dd></div>}{review.targetType && <div><dt>평가 대상</dt><dd>{targetLabels[review.targetType]}</dd></div>}{review.targetAssessmentId && <div><dt>대상 평가 ID</dt><dd><code>{review.targetAssessmentId}</code></dd></div>}
    <div><dt>요청 시점</dt><dd>{formatDate(review.requestedAt)}</dd></div><div><dt>검토 시작</dt><dd>{formatDate(review.startedAt)}</dd></div><div><dt>처리 완료</dt><dd>{formatDate(review.completedAt)}</dd></div><div><dt>데이터 버전</dt><dd><code>{review.dataVersion}</code></dd></div><div><dt>정책 버전</dt><dd><code>{review.policyVersion}</code></dd></div><div><dt>처리 결과</dt><dd>{review.resultCode ? <><strong>{resultLabels[review.resultCode]}</strong><code>{review.resultCode}</code></> : '처리 전'}</dd></div>
  </dl><div className="admin-review-card__reasons"><span>서버 사유 코드</span>{review.reasonCodes.map((code) => <code key={code}>{code}</code>)}</div>{review.demoOnly && <span className="admin-demo-chip">Demo Only</span>}</section>
}

function AdminReviewDetailPage() {
  const { reviewId = '' } = useParams()
  const [review, setReview] = useState<AdminReviewQueueItem | null>(null)
  const [resultCode, setResultCode] = useState<AdminReviewResultCode | ''>('')
  const [error, setError] = useState<ApiError | null>(null)
  const [phase, setPhase] = useState<'idle' | 'loading' | 'claiming' | 'completing'>('idle')
  const controllerRef = useRef<AbortController | null>(null)
  const sequenceRef = useRef(0)

  const commitResponse = useCallback((next: AdminReviewQueueItem) => {
    if (next.reviewId !== reviewId) throw { code: 'ADMIN_REVIEW_RESPONSE_INVALID', message: '요청한 검토 ID와 서버 응답이 일치하지 않습니다.', retryable: true } satisfies ApiError
    setReview(next)
    setResultCode(next.resultCode ?? '')
  }, [reviewId])

  const run = useCallback(async (nextPhase: 'loading' | 'claiming' | 'completing', request: (signal: AbortSignal) => Promise<{ review: AdminReviewQueueItem }>) => {
    controllerRef.current?.abort()
    const controller = new AbortController(); controllerRef.current = controller
    const sequence = ++sequenceRef.current
    setPhase(nextPhase); setError(null)
    try {
      const response = await request(controller.signal)
      if (sequence === sequenceRef.current) commitResponse(response.review)
    } catch (caught) {
      if (!controller.signal.aborted && sequence === sequenceRef.current) setError(normalizeAdminReviewError(caught))
    } finally {
      if (sequence === sequenceRef.current) setPhase('idle')
    }
  }, [commitResponse])

  const load = useCallback(() => {
    if (!reviewId) return Promise.resolve()
    return run('loading', (signal) => adminReviewProvider.get(reviewId, signal))
  }, [reviewId, run])

  useEffect(() => {
    queueMicrotask(() => void load())
    return () => { sequenceRef.current += 1; controllerRef.current?.abort() }
  }, [load])

  const options = useMemo(() => review ? allowedResults[review.triggerType] : [], [review])
  const busy = phase !== 'idle'
  const claim = () => { void run('claiming', (signal) => adminReviewProvider.claim(reviewId, signal)) }
  const complete = () => { if (resultCode) void run('completing', (signal) => adminReviewProvider.complete(reviewId, resultCode, signal)) }

  return <main id="main-content" tabIndex={-1} className="admin-main"><div className="admin-container admin-detail"><Link className="admin-back-link" to="/admin/reviews">← 검토 목록</Link><header className="admin-heading"><p>UNDERWRITER REVIEW DETAIL</p><h1>심사역 검토 상세</h1><span>서버가 등록한 검토 요청의 상태를 확인하고 확정된 결과 코드로 처리합니다.</span></header>
    <p className="admin-demo-notice">합성 Demo 데이터 전용 화면이며 별도 관리자 인증 없이 시연할 수 있습니다.</p>
    <div className="admin-detail-toolbar"><span role="status" aria-live="polite">{phase === 'loading' ? '검토 상세를 불러오고 있습니다.' : phase === 'claiming' ? '검토 요청을 접수하고 있습니다.' : phase === 'completing' ? '검토를 완료하고 있습니다.' : review ? `${statusLabels[review.status]} 상태입니다.` : error ? '검토 상세를 확인하지 못했습니다.' : '검토 상세를 확인해주세요.'}</span><button type="button" onClick={() => void load()} disabled={busy}>상태 새로고침</button></div>
      {error && <section className="admin-error" role="alert"><div><strong>{error.message}</strong><small>{error.code}{error.requestId ? ` · Request ID: ${error.requestId}` : ''}</small></div><button type="button" onClick={() => void load()}>다시 확인</button></section>}
      {phase === 'loading' && !review && <div className="admin-detail-skeleton" aria-hidden="true"><span /><span /></div>}
      {review && <><ReviewFacts review={review} /><section className="admin-review-action" aria-labelledby="review-action-title"><p>REVIEW ACTION</p><h2 id="review-action-title">검토 처리</h2>
        {review.status === 'PENDING' && <><p>이 요청을 접수하면 상태가 검토 중으로 변경됩니다.</p><button type="button" onClick={claim} disabled={busy}>{phase === 'claiming' ? '접수 중…' : '검토 접수'}</button></>}
        {review.status === 'IN_REVIEW' && <><label htmlFor="review-result">처리 결과</label><select id="review-result" value={resultCode} onChange={(event) => setResultCode(event.target.value as AdminReviewResultCode | '')} disabled={busy}><option value="">처리 결과 선택</option>{options.map((code) => <option value={code} key={code}>{resultLabels[code]} · {code}</option>)}</select><p className="admin-review-action__warning">완료 후에는 처리 결과를 변경할 수 없습니다.</p><button type="button" onClick={complete} disabled={busy || !resultCode}>{phase === 'completing' ? '완료 처리 중…' : '선택한 결과로 검토 완료'}</button></>}
        {review.status === 'COMPLETED' && <p className="admin-review-action__complete">이 검토 요청은 <strong>{review.resultCode ? resultLabels[review.resultCode] : '서버 확정 결과'}</strong>로 처리 완료되었습니다.</p>}
      </section></>}
  </div></main>
}

export default AdminReviewDetailPage
