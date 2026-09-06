import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { normalizeAdminEvidenceBurdenError } from '../api/adminEvidenceBurdenClient'
import { adminEvidenceBurdenProvider } from '../hooks/useAdminEvidenceBurdenState'
import type { AdminEvidenceBurdenResponse, EvidenceTypeBurdenBreakdown } from '../types/adminEvidenceBurden'
import type { ApiError } from '../types/api'
import type { ConsentSourceType } from '../types/consent'
import type { EvidenceResolutionStatus } from '../types/evidenceResolution'
import './AdminEvidenceBurdenPage.css'

const sourceLabels: Record<ConsentSourceType, string> = { BANK_INTERNAL: '은행 내부 데이터', CREDIT_INFORMATION: '신용정보', CUSTOMER_SUBMITTED: '고객 제출 데이터', EXTERNAL_CONNECTED: '외부 연결 데이터' }
const resolutionLabels: Record<EvidenceResolutionStatus, string> = { RESOLVED: '처리 경로 확정', MORE_EVIDENCE_REQUIRED: '추가 Evidence 필요', HUMAN_REVIEW: '심사역 검토 필요' }
const formatDate = (value: string) => new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
const collectionLabel = (value: boolean | null) => value === null ? '수집 결정 전' : value ? '수집 종료' : '수집 계속'

function MetricGroup({ id, title, description, items }: { id: string; title: string; description: string; items: Array<[string, number, string?]> }) {
  const titleId = `admin-burden-${id}-title`
  return <section className="admin-burden-group" aria-labelledby={titleId}><div><h2 id={titleId}>{title}</h2><p>{description}</p></div><dl>{items.map(([label, value, hint]) => <div key={label}><dt>{label}</dt><dd>{new Intl.NumberFormat('ko-KR').format(value)}<small>{hint ?? '건'}</small></dd></div>)}</dl></section>
}

function EvidenceBreakdown({ item }: { item: EvidenceTypeBurdenBreakdown }) {
  return <article className="admin-burden-evidence" aria-labelledby={`${item.evidenceType}-title`}><div><span>{sourceLabels[item.sourceType]}</span><h3 id={`${item.evidenceType}-title`}>{item.evidenceType}</h3><small>{formatDate(item.firstRequestedAt)}{item.firstRequestedAt !== item.lastRequestedAt ? ` – ${formatDate(item.lastRequestedAt)}` : ''}</small></div><dl><div><dt>요청</dt><dd>{item.requestCount}건</dd></div><div><dt>제출</dt><dd>{item.submissionCount}건</dd></div><div><dt>품질 통과</dt><dd>{item.acceptedCount}건</dd></div><div><dt>품질 제외</dt><dd>{item.rejectedCount}건</dd></div><div><dt>심사역 확인</dt><dd>{item.reviewRequiredCount}건</dd></div></dl></article>
}

function BurdenResult({ result }: { result: AdminEvidenceBurdenResponse }) {
  return <><section className="admin-burden-notice"><span aria-hidden="true">i</span><div><strong>정책 임계치가 적용되지 않은 사실 지표입니다</strong><p>요청 횟수와 처리 이력을 보여줄 뿐, Evidence 요청이 많거나 적절한지 판단하지 않습니다.</p></div></section><div className="admin-burden-grid">
    <MetricGroup id="requests" title="요청 현황" description="서버에 기록된 Evidence 선택 횟수입니다." items={[["전체 요청", result.evidenceRequestCount], ["반복 요청", result.repeatedRequestCount], ["최대 반복 차수", result.maxRequestIteration, '차']]}/>
    <MetricGroup id="availability" title="준비 상태" description="선택 시점에 기록된 이용 가능 상태입니다." items={[["즉시 이용 가능", result.availableRequestCount], ["요청 가능", result.requestableRequestCount], ["동의 필요", result.consentRequiredRequestCount], ["이용 불가", result.unavailableRequestCount]]}/>
    <MetricGroup id="quality" title="제출·품질 상태" description="제출 및 품질검증 이력을 상태별로 표시합니다." items={[["제출 완료", result.submissionCount], ["제출 대기", result.pendingSubmissionCount], ["품질 통과", result.acceptedCount], ["품질 제외", result.rejectedCount], ["심사역 확인", result.reviewRequiredCount], ["미검증 제출", result.unverifiedSubmissionCount], ["미통과 품질 차원", result.failedQualityDimensionCount]]}/>
    <MetricGroup id="processing" title="후속 처리" description="보완평가와 수집 결정이 실행된 횟수입니다." items={[["보완평가", result.supplementalAssessmentCount], ["수집 결정", result.resolutionCount]]}/>
  </div><section className="admin-burden-resolution" aria-labelledby="burden-resolution-title"><div><span>LATEST RESOLUTION</span><h2 id="burden-resolution-title">최근 수집 결정</h2></div><dl><div><dt>처리 상태</dt><dd>{result.latestResolutionStatus ? resolutionLabels[result.latestResolutionStatus] : '기록 없음'}</dd></div><div><dt>서버 상태 코드</dt><dd><code>{result.latestResolutionStatus ?? '기록 없음'}</code></dd></div><div><dt>Evidence 수집</dt><dd>{collectionLabel(result.collectionStopped)}</dd></div></dl></section><section className="admin-burden-breakdown" aria-labelledby="burden-breakdown-title"><div><span>EVIDENCE BREAKDOWN</span><h2 id="burden-breakdown-title">Evidence 유형별 내역</h2></div>{result.evidenceTypes.length > 0 ? <div>{result.evidenceTypes.map((item) => <EvidenceBreakdown item={item} key={item.evidenceType} />)}</div> : <p className="admin-burden-empty">기록된 Evidence 요청이 없습니다.</p>}</section><footer className="admin-burden-meta"><span>집계 기준시점 {formatDate(result.asOf)}</span><code>{result.measurementVersion}</code>{result.demoOnly && <span>Demo Only</span>}</footer></>
}

function AdminEvidenceBurdenPage() {
  const { sessionId = '' } = useParams()
  const [result, setResult] = useState<AdminEvidenceBurdenResponse | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [loading, setLoading] = useState(false)
  const controllerRef = useRef<AbortController | null>(null)
  const sequenceRef = useRef(0)

  const load = useCallback(async () => {
    if (!sessionId) return
    controllerRef.current?.abort()
    const controller = new AbortController(); controllerRef.current = controller
    const sequence = ++sequenceRef.current
    setLoading(true); setError(null)
    try {
      const response = await adminEvidenceBurdenProvider.get(sessionId, controller.signal)
      if (response.sessionId !== sessionId || response.policyThresholdApplied !== false || response.measurementVersion !== 'evidence-burden-metrics-v1') throw { code: 'ADMIN_EVIDENCE_BURDEN_RESPONSE_INVALID', message: '요청한 세션의 정책 중립적 Evidence 부담 지표를 확인할 수 없습니다.', retryable: true } satisfies ApiError
      if (sequence === sequenceRef.current) setResult(response)
    } catch (caught) {
      if (!controller.signal.aborted && sequence === sequenceRef.current) setError(normalizeAdminEvidenceBurdenError(caught))
    } finally {
      if (sequence === sequenceRef.current) setLoading(false)
    }
  }, [sessionId])

  useEffect(() => {
    queueMicrotask(() => void load())
    return () => { sequenceRef.current += 1; controllerRef.current?.abort() }
  }, [load])

  return <main id="main-content" tabIndex={-1} className="admin-main"><div className="admin-container admin-burden"><nav className="admin-burden-back" aria-label="세션 관리자 화면"><Link to="/admin/reviews">← 검토 목록</Link><Link to={`/admin/sessions/${encodeURIComponent(sessionId)}/audit`}>세션 처리 이력</Link></nav><header className="admin-heading"><p>EVIDENCE BURDEN METRICS</p><h1>Evidence 요청 부담 지표</h1><span>서버가 교차검증한 Evidence 요청·제출·품질검증·후속 처리 횟수를 확인합니다.</span></header>
    <p className="admin-demo-notice">합성 Demo 데이터 전용 화면이며 별도 관리자 인증 없이 시연할 수 있습니다.</p>
    <section className="admin-burden-context" aria-label="조회 중인 세션"><div><span>SESSION ID</span><code>{sessionId}</code></div><button type="button" onClick={() => void load()} disabled={loading}>상태 새로고침</button></section><div className="admin-live" role="status" aria-live="polite">{loading ? 'Evidence 부담 지표를 불러오고 있습니다.' : error ? 'Evidence 부담 지표를 확인하지 못했습니다.' : result ? '서버가 집계한 Evidence 부담 지표를 표시합니다.' : 'Evidence 부담 지표를 확인해주세요.'}</div>
      {error && <section className="admin-error" role="alert"><div><strong>{error.message}</strong><small>{error.code}{error.requestId ? ` · Request ID: ${error.requestId}` : ''}</small></div><button type="button" onClick={() => void load()}>다시 확인</button></section>}
      {loading && !result && <div className="admin-burden-skeleton" aria-hidden="true"><span /><span /><span /><span /></div>}
      {result && <BurdenResult result={result} />}
  </div></main>
}

export default AdminEvidenceBurdenPage
