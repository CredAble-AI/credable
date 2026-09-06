import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { normalizeEvidenceSelectionError } from '../api/evidenceSelectionClient'
import { normalizePolicyBoundaryError } from '../api/policyBoundaryClient'
import Header from '../components/Header'
import EvidenceFileSubmission from '../components/EvidenceFileSubmission'
import { isMockMode } from '../config/providerMode'
import { policyBoundaryProvider } from '../hooks/useAssessmentState'
import { useCustomerSession } from '../hooks/useCustomerSession'
import { evidenceSelectionProvider } from '../hooks/useEvidenceSelectionState'
import type { ApiError } from '../types/api'
import type { ConsentSourceType } from '../types/consent'
import type { EvidenceAvailability, EvidenceSelectionResponse, EvidenceSelectionStatus } from '../types/evidenceSelection'
import './AssessmentPage.css'
import './EvidenceSelectionPage.css'

type Phase = 'loading' | 'selecting' | 'idle'

const statusCopy: Record<EvidenceSelectionStatus, { label: string; description: string }> = {
  SELECTED: { label: '다음 Evidence 선택 완료', description: '서버가 현재 불확실한 항목을 확인할 Evidence 한 건을 선택했습니다.' },
  NOT_REQUIRED: { label: '추가 Evidence 불필요', description: '서버가 현재 경로가 안정적이라고 판단해 추가 자료를 선택하지 않았습니다.' },
  POLICY_BLOCKED: { label: '자동 선택 중단', description: '정책에 따라 Evidence 자동 선택이 중단되었습니다.' },
  HUMAN_REVIEW: { label: '심사역 확인 필요', description: '유효한 다음 Evidence를 선택하지 않고 심사역 확인 단계로 전환했습니다.' },
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
const rationaleCopy: Record<string, string> = {
  DEMO_RESOLVE_BOUNDARY_1_2: '현재 가능한 경로를 구분하는 데 필요한 항목입니다.',
  DEMO_MINIMUM_SINGLE_REQUEST: '추가 요청을 한 건으로 제한한 Demo 선택 결과입니다.',
  DEMO_CROSS_CHECK_SETTLEMENT: '정산과 입금 흐름을 교차 확인하기 위한 항목입니다.',
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
        ? evidenceSelectionProvider.selectNext(session.sessionId, controller.signal)
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
    <nav className="assessment-steps" aria-label="진행 단계"><span>시작</span><span>동의</span><span>데이터 연결</span><span>기준평가</span><strong aria-current="step">Evidence 선택</strong><span>품질 확인</span></nav>
    <header className="assessment-heading"><div>{isMockMode && <span className="assessment-badge">Mock result · Demo Only</span>}<p className="flow-kicker">MINIMUM EVIDENCE</p><h1>다음으로 확인할 자료 한 건을 보여드립니다</h1><p>서버가 현재 정책 경계를 확인하기 위해 선택한 한 건만 표시합니다. 프론트엔드는 후보를 다시 계산하거나 순위를 만들지 않습니다.</p></div><aside><span>현재 Demo 사례</span><strong>{session.demoProfile.displayName}</strong><small>{session.demoProfile.description}</small></aside></header>

    <div className="assessment-live" role="status" aria-live="polite">{phase === 'loading' ? '저장된 Evidence 선택 상태를 확인하고 있습니다.' : phase === 'selecting' ? '서버에서 다음 Evidence 한 건을 선택하고 있습니다.' : error ? 'Evidence 선택 상태를 확인하지 못했습니다.' : selection ? 'Evidence 선택 상태를 확인했습니다.' : '아직 선택된 Evidence가 없습니다.'}</div>
    {error && <section className="assessment-error" role="alert"><div><strong>{error.message}</strong><small>오류 코드: {error.code}{error.requestId ? ` · Request ID: ${error.requestId}` : ''}</small></div>{error.retryable && <button type="button" onClick={() => void requestSelection(selectNextRequested)}>다시 확인</button>}</section>}
    {phase !== 'idle' && !result && <div className="assessment-skeleton" aria-hidden="true"><span /><span /></div>}

    {!error && phase === 'idle' && !selection && <section className="evidence-empty"><span aria-hidden="true">1</span><div><h2>다음 Evidence를 아직 선택하지 않았습니다</h2><p>자동으로 요청하지 않습니다. 아래 버튼을 선택하면 서버가 현재 경계를 기준으로 한 건만 선택합니다.</p></div><button className="button button--primary" type="button" onClick={() => void requestSelection(true)}>다음 Evidence 확인</button></section>}

    {selection && copy && <>
      <section className={`assessment-result evidence-status evidence-status--${selection.status.toLowerCase()}`}><div className="assessment-result__icon" aria-hidden="true">{selection.status === 'SELECTED' ? '✓' : 'i'}</div><div><span>{selection.status}</span><h2>{copy.label}</h2><p>{copy.description}</p>{selection.stopReason && <p>서버 상태 코드 <code>{selection.stopReason}</code></p>}</div></section>
      {selectedEvidence && availability && <section className="evidence-card" aria-labelledby="selected-evidence-title"><div className="evidence-card__top"><div><span>{sourceLabels[selectedEvidence.sourceType]}</span><h2 id="selected-evidence-title">{selectedEvidence.displayName}</h2></div><span className={`evidence-availability evidence-availability--${selectedEvidence.availability.toLowerCase()}`}>{availability.label}</span></div><p>{selectedEvidence.description}</p><p className="evidence-availability-note">{availability.description}</p><section><h3>선택 근거</h3><ul>{selectedEvidence.rationaleCodes.map((code) => <li key={code}><span>{rationaleCopy[code] ?? '서버가 제공한 선택 근거입니다.'}</span><code>{code}</code></li>)}</ul></section></section>}
      {selectedEvidence && <EvidenceFileSubmission sessionId={session.sessionId} selectionId={selection.selectionId} evidenceType={selectedEvidence.evidenceType} />}
      <div className="assessment-detail-grid evidence-metadata"><section className="assessment-panel"><div className="assessment-panel__heading"><div><span>SELECTION SCOPE</span><h2>선택 범위</h2></div><span className="demo-chip">Demo Only</span></div><dl><div><dt>현재 반복 차수</dt><dd>{selection.iteration}</dd></div><div><dt>검토 후보 수</dt><dd>{selection.evaluatedCandidateCount}건</dd></div><div><dt>심사역 확인</dt><dd>{selection.underwriterRequired ? '필요' : '서버 응답상 필요 없음'}</dd></div><div><dt>선택 시점</dt><dd>{formatDate(selection.selectedAt)}</dd></div></dl><p>검토 후보 수는 서버가 비교한 후보 개수이며 순위나 추천 점수가 아닙니다.</p></section><section className="assessment-panel"><div className="assessment-panel__heading"><div><span>TRACEABILITY</span><h2>선택 메타데이터</h2></div></div><dl><div><dt>선택 ID</dt><dd>{selection.selectionId}</dd></div><div><dt>정책 경계 ID</dt><dd>{selection.boundaryCheckId}</dd></div><div><dt>보정 버전</dt><dd>{selection.calibrationVersion}</dd></div><div><dt>경계 정책 버전</dt><dd>{selection.boundaryPolicyVersion}</dd></div><div><dt>선택 정책 버전</dt><dd>{selection.selectionPolicyVersion}</dd></div></dl></section></div>
    </>}

    <section className="assessment-actions"><div><strong>{selection?.status === 'SELECTED' ? '선택된 한 건을 제출해주세요' : '서버 선택 상태를 확인해주세요'}</strong><p>{selection?.status === 'SELECTED' ? '서버가 제공한 Demo 자료를 내려받아 같은 파일을 제출하면 백엔드가 실제 파일을 검증합니다.' : '선택 결과가 없거나 자동 처리가 중단된 경우 Evidence를 임의로 고르지 않습니다.'}</p></div><div><Link className="button button--secondary" to="/assessment">기준평가로 돌아가기</Link></div></section>
  </div></main></div>
}

export default EvidenceSelectionPage
