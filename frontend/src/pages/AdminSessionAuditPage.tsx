import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { normalizeAdminAuditError } from '../api/adminAuditClient'
import AdminApiKeyForm from '../components/AdminApiKeyForm'
import { adminAuditProvider } from '../hooks/useAdminAuditState'
import { useAdminAuth } from '../hooks/useAdminAuth'
import type { AdminAuditEventListResponse, AuditActor, AuditStage, SessionAuditEvent } from '../types/adminAudit'
import type { ApiError } from '../types/api'
import './AdminSessionAuditPage.css'

const PAGE_SIZE = 20
const actorLabels: Record<AuditActor, string> = { SYSTEM: '시스템', CUSTOMER: '고객', UNDERWRITER: '심사역' }
const stageLabels: Record<AuditStage, string> = {
  SESSION_CREATED: '세션 생성', CONSENT_GRANTED: '기본 동의 완료', CONSENT_WITHDRAWN: '기본 동의 철회', DATA_SOURCE_REFRESHED: '데이터 출처 확인', ASSESSMENT_RUN: '기준평가 실행', POLICY_BOUNDARY_CHECKED: '정책 경계 확인', EVIDENCE_SELECTED: 'Evidence 선택', EVIDENCE_CONSENT_GRANTED: 'Evidence 동의 완료', EVIDENCE_CONSENT_WITHDRAWN: 'Evidence 동의 철회', EVIDENCE_SUBMITTED: 'Evidence 제출', EVIDENCE_QUALITY_CHECKED: 'Evidence 품질 확인', SUPPLEMENTAL_ASSESSMENT_RUN: '보완평가 실행', ASSESSMENT_COMPARED: '평가 전후 비교', EVIDENCE_COLLECTION_RESOLVED: 'Evidence 수집 결정', ASSESSMENT_REVIEW_REQUESTED: '평가 재확인 요청', UNDERWRITER_REVIEW_STARTED: '심사역 검토 시작', UNDERWRITER_REVIEW_COMPLETED: '심사역 검토 완료', PRODUCT_CATALOG_REFRESHED: '상품 카탈로그 확인', PRODUCT_CONDITIONS_QUERIED: '상품 조건 조회',
}
const formatDate = (value: string) => new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))

function AuditEventCard({ event }: { event: SessionAuditEvent }) {
  return <article className="admin-audit-event" aria-labelledby={`${event.eventId}-title`}><div className="admin-audit-event__heading"><div><span>{actorLabels[event.actor]}</span><h2 id={`${event.eventId}-title`}>{stageLabels[event.stage]}</h2><code>{event.stage}</code></div><time dateTime={event.timestamp}>{formatDate(event.timestamp)}</time></div><section aria-label="서버 결과 요약"><h3>결과 요약</h3>{Object.keys(event.outputSummary).length > 0 ? <dl>{Object.entries(event.outputSummary).map(([key, value]) => <div key={key}><dt>{key}</dt><dd><code>{String(value)}</code></dd></div>)}</dl> : <p>서버가 제공한 결과 요약이 없습니다.</p>}</section><details><summary>추적 정보 확인</summary><dl><div><dt>이벤트 ID</dt><dd><code>{event.eventId}</code></dd></div><div><dt>요청 ID</dt><dd><code>{event.requestId}</code></dd></div><div><dt>입력 버전</dt><dd><code>{event.inputVersion}</code></dd></div><div><dt>입력 Snapshot Hash</dt><dd><code>{event.inputSnapshotHash}</code></dd></div><div><dt>데이터 버전</dt><dd><code>{event.dataVersion ?? '기록 없음'}</code></dd></div><div><dt>모델 버전</dt><dd><code>{event.modelVersion ?? '기록 없음'}</code></dd></div><div><dt>정책 버전</dt><dd><code>{event.policyVersion ?? '기록 없음'}</code></dd></div></dl></details></article>
}

function AdminSessionAuditPage() {
  const { sessionId = '' } = useParams()
  const { apiKey, clear } = useAdminAuth()
  const [result, setResult] = useState<AdminAuditEventListResponse | null>(null)
  const [cursors, setCursors] = useState<Array<string | null>>([null])
  const [error, setError] = useState<ApiError | null>(null)
  const [loading, setLoading] = useState(false)
  const controllerRef = useRef<AbortController | null>(null)
  const sequenceRef = useRef(0)
  const cursor = cursors[cursors.length - 1] ?? null

  const load = useCallback(async () => {
    if (!apiKey || !sessionId) return
    controllerRef.current?.abort()
    const controller = new AbortController(); controllerRef.current = controller
    const sequence = ++sequenceRef.current
    setLoading(true); setError(null)
    try {
      const response = await adminAuditProvider.list(apiKey, sessionId, PAGE_SIZE, cursor, controller.signal)
      if (response.sessionId !== sessionId || response.events.some((event) => event.sessionId !== sessionId)) throw { code: 'ADMIN_AUDIT_RESPONSE_INVALID', message: '요청한 세션과 일치하는 감사 이력을 확인할 수 없습니다.', retryable: true } satisfies ApiError
      if (sequence === sequenceRef.current) setResult(response)
    } catch (caught) {
      if (!controller.signal.aborted && sequence === sequenceRef.current) setError(normalizeAdminAuditError(caught))
    } finally {
      if (sequence === sequenceRef.current) setLoading(false)
    }
  }, [apiKey, cursor, sessionId])

  useEffect(() => {
    if (apiKey) queueMicrotask(() => void load())
    return () => { sequenceRef.current += 1; controllerRef.current?.abort() }
  }, [apiKey, load])

  const resetKey = () => { clear(); setResult(null); setError(null); setCursors([null]) }
  const showNewer = () => { setResult(null); setError(null); setCursors((current) => current.slice(0, -1)) }
  const showOlder = () => {
    if (!result?.nextCursor) return
    setResult(null); setError(null); setCursors((current) => [...current, result.nextCursor])
  }
  const authFailed = error?.code === 'ADMIN_AUTHENTICATION_FAILED'
  const page = cursors.length

  return <main id="main-content" tabIndex={-1} className="admin-main"><div className="admin-container admin-audit"><Link className="admin-back-link" to="/admin/reviews">← 검토 목록</Link><header className="admin-heading"><p>SESSION AUDIT TRAIL</p><h1>세션 처리 이력</h1><span>서버가 기록한 처리 단계와 추적 메타데이터를 최신순으로 확인합니다. 원본 금융정보는 이 화면에 제공되지 않습니다.</span></header>
    {!apiKey ? <AdminApiKeyForm /> : <><section className="admin-audit-context" aria-label="조회 중인 세션"><div><span>SESSION ID</span><code>{sessionId}</code></div><button type="button" onClick={() => void load()} disabled={loading}>상태 새로고침</button></section><div className="admin-live" role="status" aria-live="polite">{loading ? `${page}페이지 감사 이력을 불러오고 있습니다.` : error ? '감사 이력을 확인하지 못했습니다.' : result ? `${page}페이지에서 ${result.events.length}건을 표시합니다.` : '감사 이력을 확인해주세요.'}</div>
      {error && <section className="admin-error" role="alert"><div><strong>{error.message}</strong><small>{error.code}{error.requestId ? ` · Request ID: ${error.requestId}` : ''}</small></div><button type="button" onClick={authFailed ? resetKey : () => void load()}>{authFailed ? '키 다시 입력' : '다시 확인'}</button></section>}
      {loading && !result && <div className="admin-audit-skeleton" aria-hidden="true"><span /><span /></div>}
      {!loading && result?.events.length === 0 && <section className="admin-empty"><h2>기록된 처리 이력이 없습니다</h2><p>이 세션에서 처리 단계가 기록되면 최신 이력부터 표시됩니다.</p></section>}
      {result && result.events.length > 0 && <section className="admin-audit-timeline" aria-label="세션 감사 이력">{result.events.map((event) => <AuditEventCard event={event} key={event.eventId} />)}</section>}
      {result && <nav className="admin-pagination" aria-label="감사 이력 페이지"><button type="button" disabled={loading || cursors.length === 1} onClick={showNewer}>최신 이력 보기</button><span>{page}페이지</span><button type="button" disabled={loading || !result.nextCursor} onClick={showOlder}>이전 이력 보기</button></nav>}
    </>}
  </div></main>
}

export default AdminSessionAuditPage
