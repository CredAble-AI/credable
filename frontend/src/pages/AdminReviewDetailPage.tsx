import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { normalizeAdminReviewError } from '../api/adminReviewClient'
import AssessmentExplanationPanel from '../components/AssessmentExplanationPanel'
import { adminReviewProvider } from '../hooks/useAdminReviewState'
import type { AssessmentUncertainty } from '../types/assessment'
import type { ApiError } from '../types/api'
import type {
  AdminReviewCaseContext,
  AdminReviewDetailResponse,
  AdminReviewQueueItem,
  AdminReviewResultCode,
  AdminReviewStatus,
  AdminReviewTriggerType,
} from '../types/adminReview'
import type { EvidenceQualityDimension, EvidenceQualityDimensionStatus } from '../types/evidenceQuality'
import './AdminReviewDetailPage.css'
import { withMinimumDuration } from '../utils/pacedRequest'

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
const reviewGuidance: Record<AdminReviewTriggerType, { title: string; description: string; action: string }> = {
  CUSTOMER_ASSESSMENT_REVIEW: { title: '고객이 평가 결과 재확인을 요청했습니다', description: '요청 시점에 확정된 평가를 확인하고 결과 유지, 정정 또는 추가 정보 필요 여부를 결정합니다.', action: '재확인 대상 평가와 서버에 저장된 결과가 일치하는지 확인' },
  POLICY_BOUNDARY: { title: '정책 경계에서 자동 판단을 완료하지 못했습니다', description: '해당 평가와 직접 연결된 정책 경계 결과를 확인하고 후속 처리를 결정합니다.', action: '평가 범위가 걸친 정책 경로와 자동 중단 사유 확인' },
  EVIDENCE_QUALITY: { title: '제출 자료에 심사역 확인이 필요한 신호가 있습니다', description: '해당 제출 파일과 여섯 가지 품질검증 결과를 확인하고 반영 또는 제외를 결정합니다.', action: '확인 필요 항목과 제출 문서의 원본성 근거 검토' },
  EVIDENCE_SELECTION: { title: '최소 증빙을 자동으로 하나로 선택하지 못했습니다', description: '해당 정책 경계와 정보 공백을 확인하고 요청할 최소 자료를 결정합니다.', action: '기존 정보와 중복되지 않는 최소 증빙 후보 확인' },
  EVIDENCE_RESOLUTION: { title: '보완평가 후에도 자동 수집 종료를 확정하지 못했습니다', description: '해당 보완평가의 전후 변화와 남은 정책 경계를 확인합니다.', action: '불확실성이 줄었는지와 추가 확인 필요 여부 결정' },
}
const assessmentStatusLabels = { NOT_RUN: '실행 전', MODEL_NOT_CONFIGURED: '평가 모델 미설정', COMPLETED: '평가 완료', INSUFFICIENT_DATA: '정보 부족', UNSUPPORTED_CUSTOMER_TYPE: '지원하지 않는 사업자 유형', FAILED: '평가 실패' } as const
const boundaryStatusLabels = { STABLE: '정책 경로 확정', AMBIGUOUS: '둘 이상의 정책 경로에 걸침', POLICY_BLOCKED: '정책상 자동 판단 중단' } as const
const selectionStatusLabels = { SELECTED: '최소 증빙 선택 완료', NOT_REQUIRED: '추가 증빙 불필요', POLICY_BLOCKED: '정책상 선택 중단', HUMAN_REVIEW: '심사역 선택 필요' } as const
const qualityStatusLabels = { ACCEPTED: '보완평가 반영 가능', REJECTED: '보완평가 반영 제외', REVIEW_REQUIRED: '심사역 확인 필요' } as const
const comparisonLabels = { NARROWED: '불확실성 감소', UNCHANGED: '변화 없음', EXPANDED: '불확실성 확대', SHIFTED: '평가 범위 이동', NOT_COMPARABLE: '비교 불가' } as const
const resolutionLabels = { RESOLVED: '추가 수집 종료', MORE_EVIDENCE_REQUIRED: '다음 자료 필요', HUMAN_REVIEW: '심사역 확인 필요' } as const
const dimensionLabels: Record<EvidenceQualityDimension, string> = { PROVENANCE: '출처', FRESHNESS: '최신성', AUTHENTICITY: '진위', COMPLETENESS: '완전성', CONSISTENCY: '일관성', MANIPULATION_RISK: '조작 위험' }
const checkStatusLabels: Record<EvidenceQualityDimensionStatus, string> = { PASSED: '확인 완료', FAILED: '확인 필요', NOT_VERIFIED: '확인되지 않음' }
const customerReasonLabels: Record<string, string> = {
  INCORRECT_INFORMATION: '평가에 사용된 정보가 실제와 다르다는 요청입니다.',
  MISSING_RECENT_INFORMATION: '최근 정보가 반영되지 않았다는 요청입니다.',
  EXCLUDED_EVIDENCE_DISPUTED: '제출 자료가 제외된 사유를 확인해 달라는 요청입니다.',
}
const rationaleLabels: Record<string, string> = {
  DEMO_SERVER_DOCUMENT_PROVENANCE_CONFIRMED: '서버 발급 기록과 문서 식별자가 일치합니다.', DEMO_SERVER_DOCUMENT_PROVENANCE_INVALID: '서버 발급 기록과 문서 식별자가 일치하지 않습니다.',
  DEMO_MANIFEST_POINT_IN_TIME_VALID: '요청된 기준 기간 안의 자료입니다.', DEMO_MANIFEST_POINT_IN_TIME_INVALID: '요청된 기준 기간을 벗어난 자료입니다.',
  DEMO_SERVER_FILE_HASH_MATCHED: '서버 기준 해시와 업로드 파일이 일치합니다.', DEMO_SERVER_FILE_HASH_NOT_VERIFIED: '서버 기준 해시와의 일치를 확인하지 못했습니다.',
  DEMO_MANIFEST_REQUIRED_FIELDS_PRESENT: '평가에 필요한 필수 항목이 모두 있습니다.', DEMO_MANIFEST_REQUIRED_FIELDS_MISSING: '평가에 필요한 필수 항목이 누락됐습니다.',
  DEMO_MANIFEST_TOTALS_CONSISTENT: '월별 내역과 합계가 일치합니다.', DEMO_MANIFEST_TOTALS_INCONSISTENT: '월별 내역과 합계가 일치하지 않습니다.',
  DEMO_FILE_METADATA_AND_HASH_UNCHANGED: '파일 형식·크기와 내용 해시에서 변경 징후가 없습니다.', DEMO_FILE_METADATA_OR_HASH_CHANGED: '파일 형식·크기 또는 내용 해시에서 변경 징후가 발견됐습니다.',
  EVIDENCE_CONSENT_NOT_ACTIVE: '해당 자료의 이용 동의가 현재 유효하지 않습니다.',
}
const evidenceTypeLabels: Record<string, string> = { CUSTOMER_SUBMITTED_RECENT_REVENUE_SUMMARY: '최근 매출·입금 요약', EXTERNAL_CONNECTED_SETTLEMENT_SUMMARY: '외부 정산 내역 요약', EXTERNAL_CONNECTED_CORPORATE_ACCOUNT_ACTIVITY: '법인 계좌 거래 요약', EXTERNAL_CONNECTED_CONTRACT_ORDER_SUMMARY: '계약·주문 내역 요약', RECENT_REVENUE_SUMMARY: '최근 매출·입금 요약' }
const formatDate = (value?: string | null) => value ? new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) : '기록 없음'
const formatBytes = (value: number) => value < 1024 * 1024 ? `${Math.ceil(value / 1024)}KB` : `${(value / (1024 * 1024)).toFixed(1)}MB`
const formatEvidenceType = (value: string) => evidenceTypeLabels[value] ?? value.toLowerCase().split('_').map((word) => word.charAt(0).toUpperCase() + word.slice(1)).join(' ')
const formatGrade = (value: string) => value.replace(/^DEMO_GRADE_/, '평가 구간 ')
const formatRoute = (value: string) => value.replace(/^DEMO_PATH_/, '정책 경로 ')
const formatUncertainty = (value: AssessmentUncertainty | null | undefined) => {
  if (!value) return '확인 가능한 범위 없음'
  if (value.gradeSet.length) return value.gradeSet.map(formatGrade).join(' · ')
  if (value.lowerBound !== null && value.upperBound !== null) return `${value.lowerBound} ~ ${value.upperBound}`
  return '확인 가능한 범위 없음'
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) { return <div><dt>{label}</dt><dd>{children}</dd></div> }

function AssessmentContext({ context }: { context: AdminReviewCaseContext }) {
  const item = context.supplementalAssessment ?? context.assessment
  if (!item) return null
  const isSupplemental = Boolean(context.supplementalAssessment)
  return <article className="admin-case-card"><header><span>{isSupplemental ? '보완평가' : '기존 은행 평가'}</span><h3>{isSupplemental ? '검증된 추가 자료를 반영한 평가' : 'CB·선택적 SCB·은행 내부정보로 산출된 평가'}</h3></header><dl className="admin-case-facts"><Fact label="처리 상태">{assessmentStatusLabels[item.status]}</Fact><Fact label="현재 확인 범위">{formatUncertainty(item.uncertainty)}</Fact><Fact label="평가 시점">{formatDate(item.calculatedAt)}</Fact></dl></article>
}

function BoundaryContext({ context }: { context: AdminReviewCaseContext }) {
  const boundary = context.boundaryCheck
  if (!boundary) return null
  return <article className="admin-case-card"><header><span>정책 경계 확인</span><h3>{boundaryStatusLabels[boundary.decision.status]}</h3></header><dl className="admin-case-facts"><Fact label="가능한 경로">{boundary.decision.possibleRoutes.length ? boundary.decision.possibleRoutes.map(formatRoute).join(' · ') : '확정된 경로 없음'}</Fact><Fact label="걸친 경계">{boundary.decision.crossedBoundaryCodes.length ? `${boundary.decision.crossedBoundaryCodes.length}개` : '없음'}</Fact><Fact label="확인 시점">{formatDate(boundary.checkedAt)}</Fact></dl>{boundary.decision.stopReason && <p className="admin-case-note">자동 중단 사유: {rationaleLabels[boundary.decision.stopReason] ?? '정책상 자동 처리를 완료할 수 없어 담당자 확인이 필요합니다.'}</p>}</article>
}

function SelectionContext({ context }: { context: AdminReviewCaseContext }) {
  const selection = context.selection
  if (!selection || context.quality) return null
  return <article className="admin-case-card"><header><span>최소 증빙 선택</span><h3>{selectionStatusLabels[selection.status]}</h3></header><dl className="admin-case-facts"><Fact label="검토한 후보">{selection.evaluatedCandidateCount}건</Fact><Fact label="확인할 정보 공백">{selection.informationGapCodes?.length ?? 0}개</Fact><Fact label="요청 차수">{selection.iteration}차 · 요청 한도 {selection.maxEvidenceRequests}건</Fact></dl>{selection.selectedEvidence && <p className="admin-case-note">선택 자료: {selection.selectedEvidence.displayName}</p>}</article>
}

function EvidenceContext({ review, context }: { review: AdminReviewQueueItem; context: AdminReviewCaseContext }) {
  const quality = context.quality; const submission = context.submission
  if (!quality && !submission) return null
  const displayName = context.selection?.selectedEvidence?.displayName ?? formatEvidenceType(quality?.evidenceType ?? submission?.evidenceType ?? review.evidenceType ?? '제출 자료')
  const file = submission?.uploadedFile
  const downloadPath = file && submission ? `/v1/sessions/${encodeURIComponent(review.sessionId)}/evidence/selections/${encodeURIComponent(submission.selectionId)}/demo-files/${encodeURIComponent(file.demoFileId)}/download` : null
  return <article className="admin-case-card admin-case-card--evidence"><header><span>제출 자료와 품질검증</span><h3>{displayName}</h3></header>{submission && <div className="admin-submitted-file"><div><span>제출 문서</span><strong>{file?.fileName ?? displayName}</strong><small>{formatDate(submission.submittedAt)}{file ? ` · PDF · ${formatBytes(file.sizeBytes)}` : ''}</small></div>{downloadPath && <a href={downloadPath} download={file?.fileName}>제출 파일 확인</a>}</div>}{quality && <><div className="admin-quality-summary"><span>품질검증 결과</span><strong>{qualityStatusLabels[quality.status]}</strong><p>{quality.eligibleForReassessment ? '검증을 통과한 정보만 보완평가에 반영할 수 있습니다.' : '현재 자료는 자동 보완평가에서 제외됩니다.'}</p></div><ul className="admin-quality-checks">{quality.checks.map((check) => <li key={check.dimension} className={`admin-quality-check admin-quality-check--${check.status.toLowerCase()}`}><div><strong>{dimensionLabels[check.dimension]}</strong><p>{rationaleLabels[check.rationaleCode] ?? '서버에 기록된 검증 기준에 따라 확인했습니다.'}</p></div><span>{checkStatusLabels[check.status]}</span></li>)}</ul></>}</article>
}

function ComparisonContext({ context }: { context: AdminReviewCaseContext }) {
  const comparison = context.comparison; const resolution = context.resolution
  if (!comparison && !resolution) return null
  return <article className="admin-case-card"><header><span>보완평가 전·후</span><h3>{comparison ? comparisonLabels[comparison.uncertaintyChange] : resolution ? resolutionLabels[resolution.status] : '확인 결과'}</h3></header>{comparison && <dl className="admin-case-facts"><Fact label="반영 전">{formatUncertainty(comparison.beforeUncertainty)}</Fact><Fact label="반영 후">{formatUncertainty(comparison.afterUncertainty)}</Fact><Fact label="비교 시점">{formatDate(comparison.comparedAt)}</Fact></dl>}{resolution && <p className="admin-case-note">후속 처리: {resolutionLabels[resolution.status]}{resolution.possibleRoutes.length ? ` · ${resolution.possibleRoutes.map(formatRoute).join(' · ')}` : ''}</p>}</article>
}

function ReviewContext({ review, context }: { review: AdminReviewQueueItem; context: AdminReviewCaseContext }) {
  const guidance = reviewGuidance[review.triggerType]; const hasContext = Object.values(context).some(Boolean)
  const customerReason = review.reasonCodes.map((code) => customerReasonLabels[code]).find(Boolean)
  return <><section className="admin-review-brief" aria-labelledby="review-reason-title"><div><span>검토 사유</span><h2 id="review-reason-title">{guidance.title}</h2><p>{guidance.description}</p>{customerReason && <p className="admin-review-brief__customer-reason"><b>고객이 지적한 내용</b> {customerReason}</p>}</div><aside><span>지금 할 일</span><strong>{guidance.action}</strong></aside></section><section className="admin-case-flow" aria-labelledby="case-flow-title"><div className="admin-section-heading"><div><span>검토 자료</span><h2 id="case-flow-title">이 요청과 직접 연결된 정보</h2><p>현재 검토 요청과 직접 연결된 서버 기록만 표시합니다.</p></div><Link to={`/admin/sessions/${encodeURIComponent(review.sessionId)}/audit`}>전체 처리 이력</Link></div>{hasContext ? <div className="admin-case-list"><AssessmentContext context={context} /><BoundaryContext context={context} /><SelectionContext context={context} /><EvidenceContext review={review} context={context} /><ComparisonContext context={context} /></div> : <p className="admin-case-flow__notice">이 검토 요청에 연결된 상세 자료를 찾지 못했습니다. 감사 이력에서 원본 기록을 확인해주세요.</p>}</section></>
}

function TechnicalDetails({ review }: { review: AdminReviewQueueItem }) {
  return <details className="admin-technical-details"><summary>감사·문의용 기술 정보</summary><p>재현이나 장애 문의에 사용하는 정보입니다. 심사 판단에는 위 검토 자료를 사용하세요.</p><dl><Fact label="검토 ID"><code>{review.reviewId}</code></Fact><Fact label="세션 ID"><code>{review.sessionId}</code></Fact><Fact label="Trigger"><code>{review.triggerType}</code></Fact><Fact label="Trigger ID"><code>{review.triggerId}</code></Fact>{review.targetAssessmentId && <Fact label="대상 평가 ID"><code>{review.targetAssessmentId}</code></Fact>}<Fact label="데이터 버전"><code>{review.dataVersion}</code></Fact><Fact label="정책 버전"><code>{review.policyVersion}</code></Fact><Fact label="서버 사유 코드">{review.reasonCodes.map((code) => <code key={code}>{code}</code>)}</Fact></dl></details>
}

function AdminReviewDetailPage() {
  const { reviewId = '' } = useParams()
  const [review, setReview] = useState<AdminReviewQueueItem | null>(null)
  const [context, setContext] = useState<AdminReviewCaseContext | null>(null)
  const [resultCode, setResultCode] = useState<AdminReviewResultCode | ''>('')
  const [decisionNote, setDecisionNote] = useState('')
  const [error, setError] = useState<ApiError | null>(null)
  const [phase, setPhase] = useState<'idle' | 'loading' | 'claiming' | 'completing'>('idle')
  const controllerRef = useRef<AbortController | null>(null); const sequenceRef = useRef(0)

  const commitResponse = useCallback((response: AdminReviewDetailResponse) => {
    if (response.review.reviewId !== reviewId) throw { code: 'ADMIN_REVIEW_RESPONSE_INVALID', message: '요청한 검토 ID와 서버 응답이 일치하지 않습니다.', retryable: true } satisfies ApiError
    setReview(response.review); setContext(response.context ?? {}); setResultCode(response.review.resultCode ?? ''); setDecisionNote(response.review.decisionNote ?? '')
  }, [reviewId])
  const run = useCallback(async (nextPhase: 'loading' | 'claiming' | 'completing', request: (signal: AbortSignal) => Promise<AdminReviewDetailResponse>) => {
    controllerRef.current?.abort(); const controller = new AbortController(); controllerRef.current = controller; const sequence = ++sequenceRef.current; setPhase(nextPhase); setError(null)
    try { const response = await request(controller.signal); if (sequence === sequenceRef.current) commitResponse(response) } catch (caught) { if (!controller.signal.aborted && sequence === sequenceRef.current) setError(normalizeAdminReviewError(caught)) } finally { if (sequence === sequenceRef.current) setPhase('idle') }
  }, [commitResponse])
  const load = useCallback(() => reviewId ? run('loading', (signal) => adminReviewProvider.get(reviewId, signal)) : Promise.resolve(), [reviewId, run])
  useEffect(() => { queueMicrotask(() => void load()); return () => { sequenceRef.current += 1; controllerRef.current?.abort() } }, [load])
  const options = useMemo(() => review ? allowedResults[review.triggerType] : [], [review]); const busy = phase !== 'idle'
  const claim = () => { void run('claiming', (signal) => withMinimumDuration(adminReviewProvider.claim(reviewId, signal))) }
  const decisionNoteText = decisionNote.trim()
  const complete = () => { if (resultCode && decisionNoteText) void run('completing', (signal) => withMinimumDuration(adminReviewProvider.complete(reviewId, resultCode, decisionNoteText, signal))) }

  return <main id="main-content" tabIndex={-1} className="admin-main"><div className="admin-container admin-detail"><Link className="admin-back-link" to="/admin/reviews">← 검토 목록</Link><header className="admin-heading"><p>UNDERWRITER REVIEW DETAIL</p><h1>심사역 검토 상세</h1><span>검토가 필요해진 이유와 해당 요청에 연결된 자료를 확인하고 최종 처리를 확정합니다.</span></header><p className="admin-demo-notice">이 화면은 시연에서만 고객 화면과 연결됩니다. 운영 환경의 심사역 시스템은 별도 권한으로 분리됩니다.</p><div className="admin-detail-toolbar"><span role="status" aria-live="polite">{phase === 'loading' ? '검토 상세를 불러오고 있습니다.' : phase === 'claiming' ? '검토를 시작하고 있습니다.' : phase === 'completing' ? '처리 결과를 저장하고 있습니다.' : review ? `${statusLabels[review.status]} 상태입니다.` : error ? '검토 상세를 확인하지 못했습니다.' : '검토 상세를 확인해주세요.'}</span><button type="button" onClick={() => void load()} disabled={busy}>최신 상태 불러오기</button></div>{error && <section className="admin-error" role="alert"><div><strong>{error.message}</strong><small>{error.code}{error.requestId ? ` · Request ID: ${error.requestId}` : ''}</small></div><button type="button" onClick={() => void load()}>다시 확인</button></section>}{phase === 'loading' && !review && <div className="admin-detail-skeleton" aria-hidden="true"><span /><span /></div>}{review && context && <><ReviewContext review={review} context={context} /><section className="admin-review-summary" aria-labelledby="review-summary-title"><div className="admin-section-heading"><div><span>검토 요청</span><h2 id="review-summary-title">현재 처리 상태</h2></div><strong className={`admin-status admin-status--${review.status.toLowerCase()}`}>{statusLabels[review.status]}</strong></div><dl><Fact label="검토 유형">{triggerLabels[review.triggerType]}</Fact>{review.targetType && <Fact label="재확인 대상">{targetLabels[review.targetType]}</Fact>}<Fact label="요청 시점">{formatDate(review.requestedAt)}</Fact><Fact label="검토 시작">{formatDate(review.startedAt)}</Fact>{review.status === 'COMPLETED' && <Fact label="최종 결과">{review.resultCode ? resultLabels[review.resultCode] : '서버 확정 결과'}</Fact>}</dl><TechnicalDetails review={review} /></section><section className="admin-ai-summary" aria-labelledby="ai-summary-title"><div className="admin-section-heading"><div><span>AI 설명</span><h2 id="ai-summary-title">서버가 확정한 결과의 요약</h2><p>기존 평가부터 증빙 검증과 재평가까지 서버가 확정한 내용을 문장으로 정리한 것입니다. 심사 판단이나 권고가 아니며, 아래 최종 처리는 심사역이 직접 결정합니다.</p></div></div><AssessmentExplanationPanel sessionId={review.sessionId} readOnly /></section><section className="admin-review-action" aria-labelledby="review-action-title"><p>심사역 최종 처리</p><h2 id="review-action-title">{review.status === 'PENDING' ? '검토를 시작해주세요' : review.status === 'IN_REVIEW' ? '확인한 결과를 선택해주세요' : '검토 처리가 완료됐습니다'}</h2>{review.status === 'PENDING' && <><p>검토를 시작하면 다른 심사역이 중복 처리하지 않도록 상태가 ‘검토 중’으로 바뀝니다.</p><button type="button" onClick={claim} disabled={busy}>{phase === 'claiming' ? '시작 처리 중…' : '검토 시작'}</button></>}{review.status === 'IN_REVIEW' && <><label htmlFor="review-result">최종 처리 결과</label><select id="review-result" value={resultCode} onChange={(event) => setResultCode(event.target.value as AdminReviewResultCode | '')} disabled={busy}><option value="">결과를 선택해주세요</option>{options.map((code) => <option value={code} key={code}>{resultLabels[code]}</option>)}</select><label htmlFor="review-note">판단 사유</label><textarea id="review-note" value={decisionNote} onChange={(event) => setDecisionNote(event.target.value)} disabled={busy} maxLength={500} rows={4} placeholder="확인한 자료와 판단 근거를 남겨주세요. 처리 이력에 함께 기록됩니다." /><small className="admin-review-action__counter">{decisionNoteText.length} / 500자</small><p className="admin-review-action__warning">확정한 후에는 처리 결과와 판단 사유를 변경할 수 없습니다.</p><button type="button" onClick={complete} disabled={busy || !resultCode || !decisionNoteText}>{phase === 'completing' ? '결과 저장 중…' : '선택한 결과로 확정'}</button></>}{review.status === 'COMPLETED' && <><p className="admin-review-action__complete">이 건의 처리 결과: <strong>{review.resultCode ? resultLabels[review.resultCode] : '서버 확정 결과'}</strong></p><div className="admin-review-action__note"><span>판단 사유</span><p>{review.decisionNote ?? '기록되지 않음'}</p></div></>}</section></>}</div></main>
}

export default AdminReviewDetailPage
