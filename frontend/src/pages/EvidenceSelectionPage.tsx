import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { normalizeEvidenceSelectionError } from '../api/evidenceSelectionClient'
import { normalizePolicyBoundaryError } from '../api/policyBoundaryClient'
import CustomerFlowSteps from '../components/CustomerFlowSteps'
import Header from '../components/Header'
import CustomerTechnicalDetails from '../components/CustomerTechnicalDetails'
import EvidenceFileSubmission from '../components/EvidenceFileSubmission'
import { policyBoundaryProvider } from '../hooks/useAssessmentState'
import { useCustomerSession } from '../hooks/useCustomerSession'
import { evidenceSelectionProvider } from '../hooks/useEvidenceSelectionState'
import type { ApiError } from '../types/api'
import type { ConsentSourceType } from '../types/consent'
import type { EvidenceAvailability, EvidenceSelectionResponse, EvidenceSelectionStatus } from '../types/evidenceSelection'
import './AssessmentPage.css'
import './EvidenceSelectionPage.css'
import { withMinimumDuration } from '../utils/pacedRequest'

type Phase = 'loading' | 'selecting' | 'idle'

const statusCopy: Record<EvidenceSelectionStatus, { label: string; description: string }> = {
  SELECTED: { label: '필요한 자료 한 건을 확인했습니다', description: '현재 결과 범위를 더 명확히 하는 데 가장 필요한 자료입니다.' },
  NOT_REQUIRED: { label: '추가 자료가 필요하지 않습니다', description: '현재 정보만으로 평가 범위가 충분히 확인됐습니다.' },
  POLICY_BLOCKED: { label: '담당자 확인이 필요합니다', description: '자동으로 자료를 요청하지 않고 담당자의 확인을 기다립니다.' },
  HUMAN_REVIEW: { label: '담당자 확인이 필요합니다', description: '추가 자료를 자동으로 요청하지 않고 담당자 확인 단계로 전환했습니다.' },
}
const availabilityCopy: Record<EvidenceAvailability, { label: string; description: string }> = {
  AVAILABLE: { label: '현재 이용 가능', description: '현재 연결 상태에서 확인할 수 있는 자료입니다.' },
  REQUESTABLE: { label: '요청 가능', description: '현재 절차에서 요청할 수 있는 자료입니다.' },
  CONSENT_REQUIRED: { label: '동의 확인 필요', description: '이용 전 데이터 동의 상태를 확인해야 하는 자료입니다.' },
  UNAVAILABLE: { label: '현재 이용 불가', description: '현재 연결 상태에서는 이용할 수 없는 자료입니다.' },
}
const sourceLabels: Record<ConsentSourceType, string> = {
  BANK_INTERNAL: '은행 내부 데이터',
  CREDIT_INFORMATION: '신용정보',
  CUSTOMER_SUBMITTED: '고객 제출 데이터',
  EXTERNAL_CONNECTED: '외부 연결 데이터',
}
const stopReasonCopy: Record<string, string> = {
  EVIDENCE_REQUEST_LIMIT_REACHED: '요청 한도까지 확인했지만 결과 범위가 하나로 좁혀지지 않아 담당자 확인으로 넘어갑니다.',
  NO_NEW_USEFUL_EVIDENCE: '이미 확인한 자료 외에 결과 범위를 좁힐 수 있는 자료가 남아 있지 않습니다.',
  NO_NOVEL_EVIDENCE: '남은 자료가 기존 평가에 이미 반영된 정보와 겹쳐 추가로 확인할 내용이 없습니다.',
  NO_USEFUL_EVIDENCE: '남은 자료로는 현재 결과 범위를 좁히기 어렵습니다.',
  NO_CANDIDATE_FOR_INFORMATION_GAP: '현재 부족한 정보를 확인할 수 있는 자료가 준비되어 있지 않습니다.',
}
const rationaleCopy: Record<string, string> = {
  DEMO_RESOLVE_BOUNDARY_1_2: '현재 가능한 경로를 구분하는 데 필요한 항목입니다.',
  DEMO_MINIMUM_SINGLE_REQUEST: '불필요한 추가 요청을 막기 위해 한 건만 선택했습니다.',
  DEMO_CROSS_CHECK_SETTLEMENT: '정산과 입금 흐름을 교차 확인하기 위한 항목입니다.',
  DEMO_CROSS_CHECK_CORPORATE_ACCOUNT: '법인 계좌의 실제 입출금 흐름을 교차 확인하기 위한 항목입니다.',
  DEMO_CROSS_CHECK_CONTRACT_ORDER: '계약·주문 실적이 실제 매출로 이어졌는지 확인하기 위한 항목입니다.',
}
const formatDate = (value: string) => new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))

function EvidenceSelectionPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const selectNextRequested = searchParams.get('selectNext') === '1'
  const { session, loading: sessionLoading } = useCustomerSession()
  const [result, setResult] = useState<EvidenceSelectionResponse | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [phase, setPhase] = useState<Phase>('loading')
  const controllerRef = useRef<AbortController | null>(null)
  const sequenceRef = useRef(0)
  const busyRef = useRef(false)

  useEffect(() => { if (!sessionLoading && !session) navigate('/start', { replace: true }) }, [navigate, session, sessionLoading])

  const requestSelection = useCallback(async (selectNext = false) => {
    if (!session || busyRef.current) return
    busyRef.current = true
    controllerRef.current?.abort()
    const controller = new AbortController(); controllerRef.current = controller
    const sequence = ++sequenceRef.current
    let stage: 'boundary' | 'selection' = 'boundary'
    let expectedBoundaryCheckId: string | null = null
    setPhase(selectNext ? 'selecting' : 'loading'); setError(null)
    try {
      if (!selectNext) {
        const boundary = await policyBoundaryProvider.get(session.sessionId, controller.signal)
        if (boundary.sessionId !== session.sessionId) throw { code: 'POLICY_BOUNDARY_SESSION_MISMATCH', message: '현재 세션의 정책 경계 결과를 확인할 수 없습니다.', retryable: true } satisfies ApiError
        if (boundary.boundaryCheck?.decision.status !== 'AMBIGUOUS') { navigate('/assessment', { replace: true }); return }
        expectedBoundaryCheckId = boundary.boundaryCheck.boundaryCheckId
      }
      stage = 'selection'
      const next = await (selectNext
        ? withMinimumDuration(evidenceSelectionProvider.selectNext(session.sessionId, controller.signal))
        : evidenceSelectionProvider.get(session.sessionId, controller.signal))
      if (next.sessionId !== session.sessionId) throw { code: 'EVIDENCE_SELECTION_SESSION_MISMATCH', message: '현재 세션의 Evidence 선택 결과를 확인할 수 없습니다.', retryable: true } satisfies ApiError
      if (next.selection && expectedBoundaryCheckId && next.selection.boundaryCheckId !== expectedBoundaryCheckId) throw { code: 'EVIDENCE_SELECTION_BOUNDARY_MISMATCH', message: '현재 정책 경계와 일치하는 Evidence 선택 결과를 확인할 수 없습니다.', retryable: true } satisfies ApiError
      if (sequence === sequenceRef.current) {
        setResult(next)
        if (selectNextRequested) setSearchParams({}, { replace: true })
      }
    } catch (caught) {
      if (!controller.signal.aborted && sequence === sequenceRef.current) {
        setError(stage === 'boundary' ? normalizePolicyBoundaryError(caught) : normalizeEvidenceSelectionError(caught))
      }
    } finally {
      if (sequence === sequenceRef.current) setPhase('idle')
      busyRef.current = false
    }
  }, [navigate, selectNextRequested, session, setSearchParams])

  useEffect(() => {
    if (session) queueMicrotask(() => void requestSelection(selectNextRequested))
    return () => { sequenceRef.current += 1; controllerRef.current?.abort(); busyRef.current = false }
  }, [requestSelection, selectNextRequested, session])

  if (sessionLoading || !session) return null
  const selection = result?.selection ?? null
  const selectedEvidence = selection?.selectedEvidence ?? null
  const copy = selection ? statusCopy[selection.status] : null
  const availability = selectedEvidence ? availabilityCopy[selectedEvidence.availability] : null

  return <div className="workspace-shell customer-flow"><Header /><main id="main-content" tabIndex={-1} className="assessment-page evidence-page"><div className="container assessment-page__inner">
    <CustomerFlowSteps current="evidence" className="assessment-steps" />
    <header className="assessment-heading"><div><h1 className="page-title-lines"><span>평가 경계의 이유를 확인하고</span><span>필요한 자료 한 건을 안내합니다</span></h1><p>불필요한 자료를 여러 개 요구하지 않고, 현재 평가의 부족한 정보를 보완할 자료 한 건만 안내합니다.</p></div><aside><span>사업자 유형</span><strong>{session.demoProfile.displayName}</strong><small>평가 주체와 사용 데이터가 이 유형에 맞게 적용됩니다.</small></aside></header>

    <div className="assessment-live" role="status" aria-live="polite">{phase === 'loading' ? '필요한 자료를 확인하고 있습니다.' : phase === 'selecting' ? '다음으로 확인할 자료 한 건을 찾고 있습니다.' : error ? '필요한 자료를 확인하지 못했습니다.' : selection ? '필요한 자료를 확인했습니다.' : '아직 선택된 자료가 없습니다.'}</div>
    {error && <section className="assessment-error" role="alert"><div><strong>{error.message}</strong><small>오류 코드: {error.code}{error.requestId ? ` · Request ID: ${error.requestId}` : ''}</small></div>{error.retryable && <button type="button" onClick={() => void requestSelection(selectNextRequested)}>다시 확인</button>}</section>}
    {phase !== 'idle' && !result && <div className="assessment-skeleton" aria-hidden="true"><span /><span /></div>}

    {!error && phase === 'idle' && !selection && <section className="evidence-empty"><span aria-hidden="true">1</span><div><h2>추가로 확인할 자료를 선택할 수 있습니다</h2><p>버튼을 누르면 현재 평가 결과를 좁히는 데 필요한 자료 한 건만 확인합니다.</p></div><button className="button button--primary" type="button" onClick={() => void requestSelection(true)}>필요한 자료 확인</button></section>}

    {selection && copy && <>
      <section className={`assessment-result evidence-status evidence-status--${selection.status.toLowerCase()}`}><div className="assessment-result__icon" aria-hidden="true">{selection.status === 'SELECTED' ? '✓' : 'i'}</div><div><span>추가 자료 확인 결과</span><h2>{copy.label}</h2><p>{copy.description}</p>{selection.stopReason && stopReasonCopy[selection.stopReason] && <p className="evidence-status__reason">{stopReasonCopy[selection.stopReason]}</p>}<p className="evidence-status__budget">요청 한도 {selection.maxEvidenceRequests}건 중 {Math.min(selection.iteration, selection.maxEvidenceRequests)}건째 확인입니다. 한도 안에서도 결과가 하나로 좁혀지지 않으면 자동으로 승인하거나 부결하지 않고 담당자 확인으로 넘어갑니다.</p></div></section>
      {selectedEvidence && availability && <section className="evidence-card" aria-labelledby="selected-evidence-title"><div className="evidence-card__top"><div><span>{sourceLabels[selectedEvidence.sourceType]}</span><h2 id="selected-evidence-title">{selectedEvidence.displayName}</h2></div><span className={`evidence-availability evidence-availability--${selectedEvidence.availability.toLowerCase()}`}>{availability.label}</span></div><p>{selectedEvidence.description}</p><p className="evidence-availability-note">{availability.description}</p><section><h3>이 자료가 필요한 이유</h3><ul>{selectedEvidence.rationaleCodes.map((code) => <li key={code}><span>{rationaleCopy[code] ?? '현재 결과 범위를 더 명확히 하는 데 필요한 자료입니다.'}</span></li>)}</ul></section></section>}
      {selectedEvidence && <EvidenceFileSubmission sessionId={session.sessionId} selectionId={selection.selectionId} evidenceType={selectedEvidence.evidenceType} displayName={selectedEvidence.displayName} consentScope={selectedEvidence.consentScope} />}
      <CustomerTechnicalDetails><dl><div><dt>처리 상태</dt><dd><code>{selection.status}</code></dd></div>{selection.stopReason && <div><dt>중단 사유</dt><dd><code>{selection.stopReason}</code></dd></div>}<div><dt>현재 확인 차수</dt><dd>{selection.iteration} / 요청 한도 {selection.maxEvidenceRequests}</dd></div><div><dt>검토 후보 수</dt><dd>{selection.evaluatedCandidateCount}건</dd></div><div><dt>담당자 확인</dt><dd>{selection.underwriterRequired ? '필요' : '필요 없음'}</dd></div><div><dt>선택 시점</dt><dd>{formatDate(selection.selectedAt)}</dd></div><div><dt>선택 ID</dt><dd><code>{selection.selectionId}</code></dd></div><div><dt>정책 경계 ID</dt><dd><code>{selection.boundaryCheckId}</code></dd></div>{selection.rejectedQualityCheckId && <div><dt>제외된 품질검증 ID</dt><dd><code>{selection.rejectedQualityCheckId}</code></dd></div>}<div><dt>보정 버전</dt><dd><code>{selection.calibrationVersion}</code></dd></div><div><dt>경계 정책 버전</dt><dd><code>{selection.boundaryPolicyVersion}</code></dd></div><div><dt>선택 정책 버전</dt><dd><code>{selection.selectionPolicyVersion}</code></dd></div>{selectedEvidence?.rationaleCodes.map((code) => <div key={code}><dt>선택 근거 코드</dt><dd><code>{code}</code></dd></div>)}</dl></CustomerTechnicalDetails>
    </>}

    <section className="assessment-actions"><div><strong>{selection?.status === 'SELECTED' ? selectedEvidence?.collectionMode === 'DEMO_CONNECTION' ? '연결된 자료를 확인해주세요' : '요청된 자료를 제출해주세요' : '추가 자료 확인 상태를 확인해주세요'}</strong><p>{selection?.status === 'SELECTED' ? selectedEvidence?.collectionMode === 'DEMO_CONNECTION' ? '동의한 범위의 연결 자료를 확인하면 서버가 기준시점과 품질을 검증합니다.' : '요청 자료를 제출하면 서버가 파일의 출처와 품질을 확인합니다.' : '자동 확인이 중단된 경우 임의의 자료를 요구하지 않습니다.'}</p></div><div>{selection?.underwriterRequired && <Link className="button button--primary" to="/admin/reviews">심사역 검토 화면 보기</Link>}<Link className="button button--secondary" to="/assessment">기존 평가로 돌아가기</Link></div></section>
  </div></main></div>
}

export default EvidenceSelectionPage
