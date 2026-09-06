import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { normalizeAdminAuditError } from '../api/adminAuditClient'
import { normalizeAdminReviewError } from '../api/adminReviewClient'
import { adminAuditProvider } from '../hooks/useAdminAuditState'
import { adminReviewProvider } from '../hooks/useAdminReviewState'
import type { AdminAuditEventListResponse, AuditStage, SessionAuditEvent } from '../types/adminAudit'
import type { ApiError } from '../types/api'
import type { AdminReviewQueueItem, AdminReviewResultCode, AdminReviewStatus, AdminReviewTriggerType } from '../types/adminReview'
import './AdminReviewDetailPage.css'

const statusLabels: Record<AdminReviewStatus, string> = { PENDING: '접수 대기', IN_REVIEW: '검토 중', COMPLETED: '처리 완료' }
const triggerLabels: Record<AdminReviewTriggerType, string> = {
  EVIDENCE_QUALITY: '증빙 품질 확인', CUSTOMER_ASSESSMENT_REVIEW: '고객 평가 재확인', POLICY_BOUNDARY: '정책 경계 확인', EVIDENCE_SELECTION: '최소 증빙 선택 확인', EVIDENCE_RESOLUTION: '증빙 수집 종료 확인',
}
const targetLabels = { BASELINE_ASSESSMENT: '기준평가', SUPPLEMENTAL_ASSESSMENT: '보완평가' } as const
const resultLabels: Record<AdminReviewResultCode, string> = {
  EVIDENCE_CONFIRMED: '증빙 확인', EVIDENCE_EXCLUDED: '증빙 제외', ASSESSMENT_CONFIRMED: '평가 확인', CORRECTION_REQUIRED: '정정 필요', ADDITIONAL_INFORMATION_REQUIRED: '추가 정보 필요', ESCALATED: '상위 검토 필요',
}
const allowedResults: Record<AdminReviewTriggerType, AdminReviewResultCode[]> = {
  EVIDENCE_QUALITY: ['EVIDENCE_CONFIRMED', 'EVIDENCE_EXCLUDED', 'ADDITIONAL_INFORMATION_REQUIRED', 'ESCALATED'],
  CUSTOMER_ASSESSMENT_REVIEW: ['ASSESSMENT_CONFIRMED', 'CORRECTION_REQUIRED', 'ADDITIONAL_INFORMATION_REQUIRED', 'ESCALATED'],
  POLICY_BOUNDARY: ['ASSESSMENT_CONFIRMED', 'CORRECTION_REQUIRED', 'ADDITIONAL_INFORMATION_REQUIRED', 'ESCALATED'],
  EVIDENCE_SELECTION: ['ASSESSMENT_CONFIRMED', 'CORRECTION_REQUIRED', 'ADDITIONAL_INFORMATION_REQUIRED', 'ESCALATED'],
  EVIDENCE_RESOLUTION: ['ASSESSMENT_CONFIRMED', 'CORRECTION_REQUIRED', 'ADDITIONAL_INFORMATION_REQUIRED', 'ESCALATED'],
}
const stageLabels: Record<AuditStage, string> = {
  SESSION_CREATED: '세션 생성', CONSENT_GRANTED: '기본 동의 완료', CONSENT_WITHDRAWN: '기본 동의 철회', DATA_SOURCE_REFRESHED: '기준평가 데이터 확인', ASSESSMENT_RUN: '기존 은행 평가 확인', POLICY_BOUNDARY_CHECKED: '정책 경계 판정', EVIDENCE_SELECTED: '최소 증빙 선택', EVIDENCE_CONSENT_GRANTED: '증빙 동의 완료', EVIDENCE_CONSENT_WITHDRAWN: '증빙 동의 철회', EVIDENCE_SUBMITTED: '증빙 제출', EVIDENCE_QUALITY_CHECKED: '증빙 품질검증', SUPPLEMENTAL_ASSESSMENT_RUN: '보완평가', ASSESSMENT_COMPARED: '보완평가 전·후 비교', EVIDENCE_COLLECTION_RESOLVED: '증빙 수집 결정', ASSESSMENT_EXPLANATION_GENERATED: '평가 설명 생성', ASSESSMENT_REVIEW_REQUESTED: '고객 재확인 요청', UNDERWRITER_REVIEW_STARTED: '심사역 검토 시작', UNDERWRITER_REVIEW_COMPLETED: '심사역 검토 완료', PRODUCT_CATALOG_REFRESHED: '상품 카탈로그 확인', PRODUCT_CONDITIONS_QUERIED: '상품 조건 조회',
}
const reviewGuidance: Record<AdminReviewTriggerType, { title: string; description: string; action: string }> = {
  CUSTOMER_ASSESSMENT_REVIEW: { title: '고객이 평가 결과 재확인을 요청했습니다', description: '서버에 확정된 기준·보완평가와 처리 이력을 비교해 결과 유지, 정정, 추가 정보 필요 여부를 확정하세요.', action: '재확인 대상 평가와 근거가 서로 일치하는지 확인' },
  POLICY_BOUNDARY: { title: '정책 경계에서 자동 판단을 완료하지 못했습니다', description: '확정된 평가 범위와 경계 사유를 확인하고 사람의 판단이 필요한지 결정하세요.', action: '평가 범위가 걸친 정책 경로와 자동 중단 사유 확인' },
  EVIDENCE_QUALITY: { title: '제출 증빙에 심사역 확인이 필요한 신호가 있습니다', description: '형식·출처·기준시점·완전성·조작 징후의 서버 검증 결과를 확인하고 반영 또는 제외를 확정하세요.', action: '검증 실패·의심 항목과 원본 확인 가능 여부 검토' },
  EVIDENCE_SELECTION: { title: '최소 증빙을 자동으로 하나로 선택하지 못했습니다', description: '정보 공백과 후보 증빙을 확인하고 고객에게 요청할 최소 자료를 결정하세요.', action: '기존 정보와 중복되지 않는 최소 증빙 후보 확인' },
  EVIDENCE_RESOLUTION: { title: '보완평가 후에도 자동 수집 종료를 확정하지 못했습니다', description: '보완평가 전·후와 남은 불확실성을 확인해 종료, 추가 정보, 상위 검토를 결정하세요.', action: '보완평가로 불확실성이 줄었는지와 남은 경계 확인' },
}
const summaryLabels: Record<string, string> = { assessmentStatus: '기준평가 상태', boundaryStatus: '정책 경계', possibleRouteCount: '가능 경로', crossedBoundaryCount: '걸친 경계', underwriterRequired: '심사역 확인', selectionStatus: '증빙 선택 상태', selectedEvidenceType: '요청 증빙', iteration: '요청 차수', qualityStatus: '품질검증 결과', evidenceType: '증빙 유형', trustStatus: '출처 확인', eligibleForReassessment: '보완평가 반영', supplementalAssessmentStatus: '보완평가 상태', uncertaintyChange: '불확실성 변화', comparisonBasis: '비교 기준' }
const formatDate = (value?: string) => value ? new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) : '기록 없음'
const humanValue = (key: string, value: string | boolean | number) => {
  if (key === 'eligibleForReassessment' && typeof value === 'boolean') return value ? '반영 가능' : '반영 제외'
  if (key === 'underwriterRequired' && typeof value === 'boolean') return value ? '필요' : '필요 없음'
  if (typeof value === 'boolean') return value ? '예' : '아니요'
  const labels: Record<string, string> = { STABLE: '경계 아님', AMBIGUOUS: '경계에 걸침', POLICY_BLOCKED: '정책상 자동 중단', ACCEPTED: '품질 통과', REJECTED: '반영 제외', REVIEW_REQUIRED: '심사역 확인 필요', NARROWED: '불확실성 감소', UNCHANGED: '변화 없음', WIDENED: '불확실성 확대', COMPLETED: '완료' }
  return labels[String(value)] ?? String(value)
}
const latestEvent = (events: SessionAuditEvent[], stages: AuditStage[]) => events.find((event) => stages.includes(event.stage))

function ProcessCard({ number, title, description, event, keys }: { number: string; title: string; description: string; event?: SessionAuditEvent; keys: string[] }) {
  const entries = event ? keys.flatMap((key) => key in event.outputSummary ? [[key, event.outputSummary[key]] as const] : []) : []
  return <article className={`admin-process-card ${event ? 'admin-process-card--complete' : ''}`}><div className="admin-process-card__heading"><span>{number}</span><div><h3>{title}</h3><p>{description}</p></div><strong>{event ? '확인됨' : '기록 전'}</strong></div>{event ? <><dl>{entries.length > 0 ? entries.map(([key, value]) => <div key={key}><dt>{summaryLabels[key] ?? key}</dt><dd>{humanValue(key, value)}</dd></div>) : <div><dt>서버 처리</dt><dd>{stageLabels[event.stage]} 완료</dd></div>}</dl><time dateTime={event.timestamp}>{formatDate(event.timestamp)}</time></> : <p className="admin-process-card__empty">이 세션에서 아직 해당 단계가 기록되지 않았습니다.</p>}</article>
}

function ReviewContext({ review, events, auditLoading, auditError }: { review: AdminReviewQueueItem; events: SessionAuditEvent[]; auditLoading: boolean; auditError: ApiError | null }) {
  const guidance = reviewGuidance[review.triggerType]
  const baseline = latestEvent(events, ['ASSESSMENT_RUN'])
  const boundary = latestEvent(events, ['POLICY_BOUNDARY_CHECKED'])
  const selection = latestEvent(events, ['EVIDENCE_SELECTED'])
  const quality = latestEvent(events, ['EVIDENCE_QUALITY_CHECKED'])
  const supplemental = latestEvent(events, ['ASSESSMENT_COMPARED', 'SUPPLEMENTAL_ASSESSMENT_RUN'])
  return <><section className="admin-review-brief" aria-labelledby="review-reason-title"><div><span>검토 사유</span><h2 id="review-reason-title">{guidance.title}</h2><p>{guidance.description}</p></div><aside><span>지금 할 일</span><strong>{guidance.action}</strong></aside></section><section className="admin-case-flow" aria-labelledby="case-flow-title"><div className="admin-section-heading"><div><span>평가 흐름</span><h2 id="case-flow-title">기준평가부터 심사역 확인까지</h2><p>서버의 세션 처리 이력을 기준으로 현재 위치와 결과를 보여줍니다.</p></div><Link to={`/admin/sessions/${encodeURIComponent(review.sessionId)}/audit`}>전체 처리 이력</Link></div>{auditLoading && <p className="admin-case-flow__notice" role="status">세션 처리 이력을 불러오고 있습니다.</p>}{auditError && <p className="admin-case-flow__notice admin-case-flow__notice--error" role="alert">상세 흐름을 불러오지 못했습니다. 검토 요청 처리는 계속할 수 있습니다.</p>}{!auditLoading && !auditError && <div className="admin-process-grid"><ProcessCard number="1" title="기존 은행 평가" description="CB·선택적 SCB·은행 내부정보로 이미 산출된 평가" event={baseline} keys={['assessmentStatus']} /><ProcessCard number="2" title="정책 경계 확인" description="현재 평가 범위가 하나의 정책 경로로 확정되는지 확인" event={boundary} keys={['boundaryStatus', 'possibleRouteCount', 'crossedBoundaryCount', 'underwriterRequired']} /><ProcessCard number="3" title="최소 증빙·품질검증" description="불확실할 때만 증빙 한 건을 요청하고 반영 가능성을 검증" event={quality ?? selection} keys={quality ? ['evidenceType', 'qualityStatus', 'trustStatus', 'eligibleForReassessment'] : ['selectionStatus', 'selectedEvidenceType', 'iteration', 'underwriterRequired']} /><ProcessCard number="4" title="보완평가 전·후" description="검증된 정보만 반영해 불확실성 변화와 남은 경계를 확인" event={supplemental} keys={['supplementalAssessmentStatus', 'uncertaintyChange', 'comparisonBasis']} /></div>}</section></>
}

function TechnicalDetails({ review }: { review: AdminReviewQueueItem }) {
  return <details className="admin-technical-details"><summary>추적·버전 정보</summary><dl><div><dt>검토 ID</dt><dd><code>{review.reviewId}</code></dd></div><div><dt>세션 ID</dt><dd><code>{review.sessionId}</code></dd></div><div><dt>Trigger</dt><dd><code>{review.triggerType}</code></dd></div><div><dt>Trigger ID</dt><dd><code>{review.triggerId}</code></dd></div>{review.evidenceType && <div><dt>증빙 유형</dt><dd><code>{review.evidenceType}</code></dd></div>}{review.targetAssessmentId && <div><dt>대상 평가 ID</dt><dd><code>{review.targetAssessmentId}</code></dd></div>}<div><dt>데이터 버전</dt><dd><code>{review.dataVersion}</code></dd></div><div><dt>정책 버전</dt><dd><code>{review.policyVersion}</code></dd></div><div><dt>서버 사유 코드</dt><dd>{review.reasonCodes.map((code) => <code key={code}>{code}</code>)}</dd></div></dl></details>
}

function AdminReviewDetailPage() {
  const { reviewId = '' } = useParams()
  const [review, setReview] = useState<AdminReviewQueueItem | null>(null)
  const [audit, setAudit] = useState<AdminAuditEventListResponse | null>(null)
  const [resultCode, setResultCode] = useState<AdminReviewResultCode | ''>('')
  const [error, setError] = useState<ApiError | null>(null)
  const [auditError, setAuditError] = useState<ApiError | null>(null)
  const [auditLoading, setAuditLoading] = useState(false)
  const [phase, setPhase] = useState<'idle' | 'loading' | 'claiming' | 'completing'>('idle')
  const controllerRef = useRef<AbortController | null>(null)
  const auditControllerRef = useRef<AbortController | null>(null)
  const sequenceRef = useRef(0)
  const auditSequenceRef = useRef(0)

  const refreshAudit = useCallback(async (sessionId: string) => {
    auditControllerRef.current?.abort()
    const controller = new AbortController(); auditControllerRef.current = controller
    const sequence = ++auditSequenceRef.current
    setAuditLoading(true); setAuditError(null)
    try {
      const response = await adminAuditProvider.list(sessionId, 100, null, controller.signal)
      if (response.sessionId !== sessionId || response.events.some((event) => event.sessionId !== sessionId)) throw { code: 'ADMIN_AUDIT_RESPONSE_INVALID', message: '현재 검토 세션과 일치하는 처리 이력을 확인할 수 없습니다.', retryable: true } satisfies ApiError
      if (sequence === auditSequenceRef.current) setAudit(response)
    } catch (caught) { if (!controller.signal.aborted && sequence === auditSequenceRef.current) setAuditError(normalizeAdminAuditError(caught)) }
    finally { if (sequence === auditSequenceRef.current) setAuditLoading(false) }
  }, [])
  const commitResponse = useCallback((next: AdminReviewQueueItem) => {
    if (next.reviewId !== reviewId) throw { code: 'ADMIN_REVIEW_RESPONSE_INVALID', message: '요청한 검토 ID와 서버 응답이 일치하지 않습니다.', retryable: true } satisfies ApiError
    setReview(next); setResultCode(next.resultCode ?? ''); void refreshAudit(next.sessionId)
  }, [refreshAudit, reviewId])
  const run = useCallback(async (nextPhase: 'loading' | 'claiming' | 'completing', request: (signal: AbortSignal) => Promise<{ review: AdminReviewQueueItem }>) => {
    controllerRef.current?.abort(); const controller = new AbortController(); controllerRef.current = controller; const sequence = ++sequenceRef.current; setPhase(nextPhase); setError(null)
    try { const response = await request(controller.signal); if (sequence === sequenceRef.current) commitResponse(response.review) } catch (caught) { if (!controller.signal.aborted && sequence === sequenceRef.current) setError(normalizeAdminReviewError(caught)) } finally { if (sequence === sequenceRef.current) setPhase('idle') }
  }, [commitResponse])
  const load = useCallback(() => reviewId ? run('loading', (signal) => adminReviewProvider.get(reviewId, signal)) : Promise.resolve(), [reviewId, run])
  useEffect(() => { queueMicrotask(() => void load()); return () => { sequenceRef.current += 1; auditSequenceRef.current += 1; controllerRef.current?.abort(); auditControllerRef.current?.abort() } }, [load])
  const options = useMemo(() => review ? allowedResults[review.triggerType] : [], [review])
  const busy = phase !== 'idle'
  const claim = () => { void run('claiming', (signal) => adminReviewProvider.claim(reviewId, signal)) }
  const complete = () => { if (resultCode) void run('completing', (signal) => adminReviewProvider.complete(reviewId, resultCode, signal)) }

  return <main id="main-content" tabIndex={-1} className="admin-main"><div className="admin-container admin-detail"><Link className="admin-back-link" to="/admin/reviews">← 검토 목록</Link><header className="admin-heading"><p>UNDERWRITER REVIEW DETAIL</p><h1>심사역 검토 상세</h1><span>검토가 필요해진 이유와 평가 흐름을 확인하고 최종 처리를 확정합니다.</span></header><p className="admin-demo-notice">이 화면은 시연에서만 고객 화면과 연결됩니다. 운영 환경의 심사역 시스템은 별도 권한으로 분리됩니다.</p><div className="admin-detail-toolbar"><span role="status" aria-live="polite">{phase === 'loading' ? '검토 상세를 불러오고 있습니다.' : phase === 'claiming' ? '검토를 시작하고 있습니다.' : phase === 'completing' ? '처리 결과를 저장하고 있습니다.' : review ? `${statusLabels[review.status]} 상태입니다.` : error ? '검토 상세를 확인하지 못했습니다.' : '검토 상세를 확인해주세요.'}</span><button type="button" onClick={() => void load()} disabled={busy}>최신 상태 불러오기</button></div>{error && <section className="admin-error" role="alert"><div><strong>{error.message}</strong><small>{error.code}{error.requestId ? ` · Request ID: ${error.requestId}` : ''}</small></div><button type="button" onClick={() => void load()}>다시 확인</button></section>}{phase === 'loading' && !review && <div className="admin-detail-skeleton" aria-hidden="true"><span /><span /></div>}{review && <><ReviewContext review={review} events={audit?.events ?? []} auditLoading={auditLoading} auditError={auditError} /><section className="admin-review-summary" aria-labelledby="review-summary-title"><div className="admin-section-heading"><div><span>검토 요청</span><h2 id="review-summary-title">현재 처리 상태</h2></div><strong className={`admin-status admin-status--${review.status.toLowerCase()}`}>{statusLabels[review.status]}</strong></div><dl><div><dt>검토 유형</dt><dd>{triggerLabels[review.triggerType]}</dd></div>{review.targetType && <div><dt>재확인 대상</dt><dd>{targetLabels[review.targetType]}</dd></div>}<div><dt>요청 시점</dt><dd>{formatDate(review.requestedAt)}</dd></div><div><dt>검토 시작</dt><dd>{formatDate(review.startedAt)}</dd></div>{review.status === 'COMPLETED' && <div><dt>최종 결과</dt><dd>{review.resultCode ? resultLabels[review.resultCode] : '서버 확정 결과'}</dd></div>}</dl><TechnicalDetails review={review} /></section><section className="admin-review-action" aria-labelledby="review-action-title"><p>심사역 최종 처리</p><h2 id="review-action-title">{review.status === 'PENDING' ? '검토를 시작해주세요' : review.status === 'IN_REVIEW' ? '확인한 결과를 선택해주세요' : '검토 처리가 완료됐습니다'}</h2>{review.status === 'PENDING' && <><p>검토를 시작하면 다른 심사역이 중복 처리하지 않도록 상태가 ‘검토 중’으로 바뀝니다.</p><button type="button" onClick={claim} disabled={busy}>{phase === 'claiming' ? '시작 처리 중…' : '검토 시작'}</button></>}{review.status === 'IN_REVIEW' && <><label htmlFor="review-result">최종 처리 결과</label><select id="review-result" value={resultCode} onChange={(event) => setResultCode(event.target.value as AdminReviewResultCode | '')} disabled={busy}><option value="">결과를 선택해주세요</option>{options.map((code) => <option value={code} key={code}>{resultLabels[code]}</option>)}</select><p className="admin-review-action__warning">확정한 후에는 처리 결과를 변경할 수 없습니다.</p><button type="button" onClick={complete} disabled={busy || !resultCode}>{phase === 'completing' ? '결과 저장 중…' : '선택한 결과로 확정'}</button></>}{review.status === 'COMPLETED' && <p className="admin-review-action__complete">이 건은 <strong>{review.resultCode ? resultLabels[review.resultCode] : '서버 확정 결과'}</strong>로 처리됐습니다.</p>}</section></>}</div></main>
}

export default AdminReviewDetailPage
