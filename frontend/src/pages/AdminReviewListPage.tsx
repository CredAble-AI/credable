import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { normalizeAdminReviewError } from '../api/adminReviewClient'
import AdminApiKeyForm from '../components/AdminApiKeyForm'
import { useAdminAuth } from '../hooks/useAdminAuth'
import { adminReviewProvider } from '../hooks/useAdminReviewState'
import type { ApiError } from '../types/api'
import type { AdminReviewQueueItem, AdminReviewQueueResponse, AdminReviewStatus } from '../types/adminReview'

const PAGE_SIZE = 20
const statusLabels: Record<AdminReviewStatus, string> = { PENDING: '접수 대기', IN_REVIEW: '검토 중', COMPLETED: '처리 완료' }
const triggerLabels = {
  EVIDENCE_QUALITY: 'Evidence 품질검토',
  CUSTOMER_ASSESSMENT_REVIEW: '고객 평가 재확인',
  POLICY_BOUNDARY: '정책 경계 검토',
  EVIDENCE_SELECTION: '최소 증빙 선택 검토',
  EVIDENCE_RESOLUTION: '증빙 수집 종료 검토',
} as const
const targetLabels = { BASELINE_ASSESSMENT: '기준평가', SUPPLEMENTAL_ASSESSMENT: '보완평가' } as const
const formatDate = (value: string) => new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))

function ReviewCard({ review }: { review: AdminReviewQueueItem }) {
  return <article className="admin-review-card" aria-labelledby={`${review.reviewId}-title`}>
    <div className="admin-review-card__heading"><div><span>{triggerLabels[review.triggerType]}</span><h2 id={`${review.reviewId}-title`}>{review.reviewId}</h2></div><strong className={`admin-status admin-status--${review.status.toLowerCase()}`}>{statusLabels[review.status]}</strong></div>
    <dl><div><dt>세션 ID</dt><dd><code>{review.sessionId}</code></dd></div><div><dt>요청 시점</dt><dd>{formatDate(review.requestedAt)}</dd></div><div><dt>검토 Trigger</dt><dd><code>{review.triggerType}</code></dd></div>{review.evidenceType && <div><dt>Evidence 유형</dt><dd><code>{review.evidenceType}</code></dd></div>}{review.targetType && <div><dt>평가 대상</dt><dd>{targetLabels[review.targetType]}</dd></div>}{review.targetAssessmentId && <div><dt>대상 평가 ID</dt><dd><code>{review.targetAssessmentId}</code></dd></div>}<div><dt>처리 결과</dt><dd><code>{review.resultCode ?? '처리 전'}</code></dd></div><div><dt>정책 버전</dt><dd><code>{review.policyVersion}</code></dd></div></dl>
    <div className="admin-review-card__reasons"><span>서버 사유 코드</span>{review.reasonCodes.map((code) => <code key={code}>{code}</code>)}</div>
    {review.demoOnly && <span className="admin-demo-chip">Demo Only</span>}
    <Link className="admin-review-card__link" to={`/admin/reviews/${encodeURIComponent(review.reviewId)}`}>상세 확인</Link>
  </article>
}

function AdminReviewListPage() {
  const { apiKey, clear } = useAdminAuth()
  const [status, setStatus] = useState<AdminReviewStatus | null>(null)
  const [offset, setOffset] = useState(0)
  const [result, setResult] = useState<AdminReviewQueueResponse | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [loading, setLoading] = useState(false)
  const controllerRef = useRef<AbortController | null>(null)
  const sequenceRef = useRef(0)

  const load = useCallback(async () => {
    if (!apiKey) return
    controllerRef.current?.abort()
    const controller = new AbortController(); controllerRef.current = controller
    const sequence = ++sequenceRef.current
    setLoading(true); setError(null); setResult(null)
    try {
      const query = { limit: PAGE_SIZE, offset, status }
      const response = await adminReviewProvider.list(apiKey, query, controller.signal)
      if (response.demoOnly !== true || response.limit !== query.limit || response.offset !== query.offset) throw { code: 'ADMIN_REVIEW_RESPONSE_INVALID', message: '요청한 페이지와 일치하는 검토 목록을 확인할 수 없습니다.', retryable: true } satisfies ApiError
      if (sequence === sequenceRef.current) setResult(response)
    } catch (caught) {
      if (!controller.signal.aborted && sequence === sequenceRef.current) setError(normalizeAdminReviewError(caught))
    } finally {
      if (sequence === sequenceRef.current) setLoading(false)
    }
  }, [apiKey, offset, status])

  useEffect(() => {
    if (apiKey) queueMicrotask(() => void load())
    return () => { sequenceRef.current += 1; controllerRef.current?.abort() }
  }, [apiKey, load])

  const resetKey = () => { clear(); setResult(null); setError(null); setOffset(0) }
  const authFailed = error?.code === 'ADMIN_AUTHENTICATION_FAILED'

  return <main id="main-content" tabIndex={-1} className="admin-main"><div className="admin-container">
      <header className="admin-heading"><p>UNDERWRITER REVIEW QUEUE</p><h1>심사역 검토 목록</h1><span>서버가 자동 판단을 중단한 건과 고객이 재확인을 요청한 건을 최신순으로 확인합니다.</span></header>
      {!apiKey ? <AdminApiKeyForm /> : <>
        <section className="admin-toolbar" aria-label="검토 목록 도구"><label>처리 상태<select value={status ?? 'ALL'} onChange={(event) => { setStatus(event.target.value === 'ALL' ? null : event.target.value as AdminReviewStatus); setOffset(0) }}><option value="ALL">전체 상태</option><option value="PENDING">접수 대기</option><option value="IN_REVIEW">검토 중</option><option value="COMPLETED">처리 완료</option></select></label><button type="button" onClick={() => void load()} disabled={loading}>상태 새로고침</button></section>
        <div className="admin-live" role="status" aria-live="polite">{loading ? '심사역 검토 목록을 불러오고 있습니다.' : error ? '검토 목록을 확인하지 못했습니다.' : result ? `전체 ${result.totalCount}건 중 ${result.items.length}건을 표시합니다.` : '검토 목록을 확인해주세요.'}</div>
        {error && <section className="admin-error" role="alert"><div><strong>{error.message}</strong><small>{error.code}{error.requestId ? ` · Request ID: ${error.requestId}` : ''}</small></div><button type="button" onClick={authFailed ? resetKey : () => void load()}>{authFailed ? '키 다시 입력' : '다시 확인'}</button></section>}
        {loading && <div className="admin-skeleton" aria-hidden="true"><span /><span /></div>}
        {!loading && result?.items.length === 0 && <section className="admin-empty"><h2>해당 상태의 검토 요청이 없습니다</h2><p>서버에 새로운 검토 요청이 등록되면 이 목록에서 확인할 수 있습니다.</p></section>}
        {!loading && result && result.items.length > 0 && <section className="admin-review-grid" aria-label="심사역 검토 요청">{result.items.map((review) => <ReviewCard review={review} key={review.reviewId} />)}</section>}
        {result && <nav className="admin-pagination" aria-label="검토 목록 페이지"><button type="button" disabled={loading || result.offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>이전 페이지</button><span>{result.totalCount === 0 ? '0건' : `${result.offset + 1}–${result.offset + result.items.length} / ${result.totalCount}건`}</span><button type="button" disabled={loading || result.offset + result.items.length >= result.totalCount} onClick={() => setOffset(offset + PAGE_SIZE)}>다음 페이지</button></nav>}
      </>}
    </div></main>
}

export default AdminReviewListPage
