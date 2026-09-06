import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { normalizeAssessmentError } from '../api/assessmentClient'
import { normalizeEvidenceSelectionError } from '../api/evidenceSelectionClient'
import { normalizePolicyBoundaryError } from '../api/policyBoundaryClient'
import AssessmentExplanationPanel from '../components/AssessmentExplanationPanel'
import AssessmentReviewPanel from '../components/AssessmentReviewPanel'
import CustomerTechnicalDetails from '../components/CustomerTechnicalDetails'
import CustomerFlowSteps from '../components/CustomerFlowSteps'
import Header from '../components/Header'
import { assessmentProvider, policyBoundaryProvider } from '../hooks/useAssessmentState'
import { useCustomerSession } from '../hooks/useCustomerSession'
import { evidenceSelectionProvider } from '../hooks/useEvidenceSelectionState'
import type { ApiError } from '../types/api'
import type { AssessmentResponse, AssessmentState, AssessmentStatus } from '../types/assessment'
import type { EvidenceSelectionResponse, EvidenceSelectionState } from '../types/evidenceSelection'
import type { BoundaryStatus, PolicyBoundaryCheckResponse, PolicyBoundaryCheckState } from '../types/policyBoundary'
import { assessmentGradeLabel } from '../utils/assessmentDisplay'
import './AssessmentPage.css'
import { withMinimumDuration } from '../utils/pacedRequest'

type Phase = 'loading' | 'running' | 'checking' | 'selecting' | 'idle'
type ErrorStage = 'load' | 'run' | 'boundary-load' | 'boundary-check' | 'selection'

const statusCopy: Record<AssessmentStatus, { label: string; icon: string; description: string }> = {
  NOT_RUN: { label: '기존 평가 확인 준비', icon: '…', description: '연결된 정보에서 은행의 기존 평가 결과를 불러올 수 있습니다.' },
  MODEL_NOT_CONFIGURED: { label: '평가 방식 미구성', icon: '○', description: '현재 환경에는 이 사업자 유형의 평가 방식이 구성되지 않았습니다.' },
  COMPLETED: { label: '기존 은행 평가 확인 완료', icon: '✓', description: '기존 CB·SCB와 은행 내부 평가 결과에서 확인된 범위와 다음 단계를 안내합니다.' },
  INSUFFICIENT_DATA: { label: '현재 데이터로 확인 불가', icon: 'i', description: '확인된 데이터만으로는 은행의 기존 평가를 확인할 수 없습니다.' },
  UNSUPPORTED_CUSTOMER_TYPE: { label: '지원 대상 확인 필요', icon: '–', description: '현재 확인 방식이 지원하지 않는 사업자 유형입니다.' },
  FAILED: { label: '기존 평가 확인 실패', icon: '!', description: '일시적인 문제로 평가를 확인하지 못했습니다. 다시 실행할 수 있습니다.' },
}

const boundaryCopy: Record<BoundaryStatus, { label: string; description: string }> = {
  STABLE: { label: '추가 자료 없이 확인 완료', description: '현재 정보만으로 평가 범위가 충분히 확인되어 추가 자료가 필요하지 않습니다.' },
  AMBIGUOUS: { label: '추가 자료 확인 필요', description: '현재 평가 범위가 정책 경계에 걸쳐 있어, 부족한 정보를 확인할 자료 한 건을 요청합니다.' },
  POLICY_BLOCKED: { label: '담당자 확인 필요', description: '자동으로 다음 단계를 정하지 않고 담당자의 확인이 필요한 상태입니다.' },
}
const restrictedBoundaryCopy = { label: '대출정책상 제한 확인', description: '은행의 사업자금 대출정책에서 확인된 제한이라 추가 자료로는 해소되지 않습니다. 자료를 요청하지 않고 제한 사유와 다음 절차를 안내합니다.' }
const restrictionReasonCopy: Record<string, string> = {
  DEMO_POLICY_RESTRICTION_ACTIVE_DELINQUENCY: '현재 진행 중인 연체가 확인되어 사업자금 대출정책상 신규 취급이 제한되는 상태입니다.',
}
const followUpCopy: Record<string, string> = {
  DEMO_FOLLOW_UP_RESOLVE_DELINQUENCY: '연체가 해소된 뒤 다시 조회하면 그 시점의 정보로 새로 확인합니다.',
  DEMO_FOLLOW_UP_BRANCH_CONSULTATION: '영업점이나 담당자 상담을 통해 다른 방법이 있는지 확인할 수 있습니다.',
}

const informationGapCopy: Record<string, string> = {
  DEMO_INFORMATION_GAP: '현재 평가에 필요한 일부 정보가 확인되지 않았습니다.',
  DEMO_RECENT_PERFORMANCE_NOT_REFLECTED: '기존 평가 기준시점 이후의 최근 매출·입금 흐름이 반영되지 않았습니다.',
  DEMO_FINANCIAL_HISTORY_THIN: '확인 가능한 재무 이력이 짧아 최근 영업 흐름을 추가로 확인해야 합니다.',
}

const formatDate = (value: string | null) => value
  ? new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
  : '확인되지 않음'
const formatValue = (value: number) => new Intl.NumberFormat('ko-KR').format(value)

const validateAssessment = (result: AssessmentResponse, sessionId: string) => {
  if (result.sessionId !== sessionId) throw {
    code: 'ASSESSMENT_SESSION_MISMATCH',
    message: '현재 세션의 기존 평가 결과를 확인할 수 없습니다.',
    retryable: true,
  } satisfies ApiError
}

const validateBoundary = (result: PolicyBoundaryCheckResponse, assessment: AssessmentState, sessionId: string) => {
  if (result.sessionId !== sessionId) throw {
    code: 'POLICY_BOUNDARY_SESSION_MISMATCH',
    message: '현재 세션의 정책 경계 결과를 확인할 수 없습니다.',
    retryable: true,
  } satisfies ApiError
  const boundary = result.boundaryCheck
  if (boundary && (boundary.assessmentId !== assessment.assessmentId || boundary.inputSnapshotId !== assessment.inputSnapshotId)) throw {
    code: 'POLICY_BOUNDARY_ASSESSMENT_MISMATCH',
    message: '현재 기존 평가와 일치하는 정책 경계 결과를 확인할 수 없습니다.',
    retryable: true,
  } satisfies ApiError
}

const validateSelection = (result: EvidenceSelectionResponse, boundaryCheckId: string, sessionId: string) => {
  if (result.sessionId !== sessionId) throw {
    code: 'EVIDENCE_SELECTION_SESSION_MISMATCH',
    message: '현재 세션의 요청 자료를 확인할 수 없습니다.',
    retryable: true,
  } satisfies ApiError
  if (result.selection && result.selection.boundaryCheckId !== boundaryCheckId) throw {
    code: 'EVIDENCE_SELECTION_BOUNDARY_MISMATCH',
    message: '현재 평가 경계와 일치하는 요청 자료를 확인할 수 없습니다.',
    retryable: true,
  } satisfies ApiError
}

function UncertaintyPanel({ state }: { state: AssessmentState }) {
  const uncertainty = state.uncertainty
  if (!uncertainty) return null
  const labels = uncertainty.gradeSet.map(assessmentGradeLabel)
  return <section className="assessment-panel assessment-uncertainty" aria-labelledby="uncertainty-title">
    <div className="assessment-panel__heading"><div><span>평가 범위</span><h2 id="uncertainty-title">현재 확인 가능한 결과</h2></div></div>
    <p>은행이 보유한 CB·선택적 SCB·내부 평가 결과에서 현재 확인된 범위입니다.</p>
    {labels.length > 0 ? <div className="assessment-range" aria-label={`현재 평가 범위: ${labels.join('에서 ')}`}>
      <div className="assessment-range__summary"><span>현재 평가 범위</span><strong>{labels.join(' ~ ')}</strong></div>
      <div className="assessment-range__track">{labels.map((label, index) => <div className="assessment-range__segment" key={uncertainty.gradeSet[index]}><span>{label}</span>{index < labels.length - 1 && <i aria-hidden="true"><b>정책 경계</b></i>}</div>)}</div>
      <p>막대 전체가 현재 확인된 범위이며, 세로선은 처리 결과가 달라질 수 있는 정책 경계입니다.</p>
    </div> : <p className="assessment-range__empty">확인 가능한 평가 구간이 없습니다.</p>}
    {(uncertainty.pointEstimate !== null || uncertainty.lowerBound !== null || uncertainty.upperBound !== null) && <dl>
      {uncertainty.pointEstimate !== null && <div><dt>모델 추정값</dt><dd>{formatValue(uncertainty.pointEstimate)}</dd></div>}
      {(uncertainty.lowerBound !== null || uncertainty.upperBound !== null) && <div><dt>추정 범위</dt><dd>{uncertainty.lowerBound !== null && uncertainty.upperBound !== null ? `${formatValue(uncertainty.lowerBound)} ~ ${formatValue(uncertainty.upperBound)}` : formatValue((uncertainty.lowerBound ?? uncertainty.upperBound) as number)}</dd></div>}
    </dl>}
    <CustomerTechnicalDetails><dl><div><dt>보정 방식</dt><dd><code>{uncertainty.calibrationMode}</code></dd></div><div><dt>보정 버전</dt><dd><code>{uncertainty.calibrationVersion}</code></dd></div></dl></CustomerTechnicalDetails>
  </section>
}

function BoundaryPanel({ boundary, selection }: { boundary: PolicyBoundaryCheckState; selection: EvidenceSelectionState | null }) {
  const restrictionCode = boundary.decision.restrictionCode ?? null
  const followUpCodes = boundary.decision.followUpCodes ?? []
  const copy = restrictionCode ? restrictedBoundaryCopy : boundaryCopy[boundary.decision.status]
  const evidence = selection?.selectedEvidence ?? null
  const gaps = selection?.informationGapCodes ?? []
  return <section className={`assessment-boundary assessment-boundary--${boundary.decision.status.toLowerCase()}`} aria-labelledby="boundary-title">
    <div className="assessment-panel__heading"><div><span>다음 단계</span><h2 id="boundary-title">{copy.label}</h2></div></div>
    <p>{copy.description}</p>
    {restrictionCode && <div className="assessment-boundary__restriction">
      <div><span>제한 사유</span><p>{restrictionReasonCopy[restrictionCode] ?? '은행의 대출정책에서 확인된 제한입니다.'}</p></div>
      {followUpCodes.length > 0 && <div><span>가능한 다음 절차</span><ul>{followUpCodes.map((code) => <li key={code}>{followUpCopy[code] ?? '담당 창구에서 다음 절차를 확인할 수 있습니다.'}</li>)}</ul></div>}
      <p className="assessment-boundary__assurance">이 상태는 신용이 낮다는 뜻도, 정보가 부족하다는 뜻도 아닙니다. 대출정책에서 확인된 제한이므로 추가 자료를 요청하지 않습니다.</p>
    </div>}
    {boundary.decision.status === 'AMBIGUOUS' && <div className="assessment-boundary__reason">
      <div><span>정책 경계 판정</span><strong>현재 결과가 둘 이상의 처리 구간에 걸쳐 있습니다.</strong><p>최소한의 정보만 더 확인해 결과 범위를 좁힙니다.</p></div>
      <div><span>현재 부족한 정보</span>{gaps.length > 0 ? <ul>{gaps.map((code) => <li key={code}>{informationGapCopy[code] ?? '기존 평가에 반영되지 않은 추가 정보가 필요합니다.'}</li>)}</ul> : <p>요청할 정보를 선택하고 있습니다.</p>}</div>
    </div>}
    {boundary.decision.status === 'AMBIGUOUS' && evidence && <div className="assessment-request-card"><div><span>요청할 최소 증빙 1건</span><h3>{evidence.displayName}</h3><p>{evidence.description}</p></div><Link className="button button--primary" to="/evidence">요청 자료 제출하기</Link></div>}
    {boundary.decision.status === 'AMBIGUOUS' && !evidence && <p className="assessment-boundary__pending" role="status">부족한 정보를 확인할 최소 증빙을 선택하고 있습니다.</p>}
    <CustomerTechnicalDetails><dl><div><dt>처리 상태</dt><dd><code>{boundary.decision.status}</code></dd></div><div><dt>가능 경로</dt><dd>{boundary.decision.possibleRoutes.length > 0 ? boundary.decision.possibleRoutes.join(', ') : '없음'}</dd></div><div><dt>정책 경계</dt><dd>{boundary.decision.crossedBoundaryCodes.length > 0 ? boundary.decision.crossedBoundaryCodes.join(', ') : '없음'}</dd></div><div><dt>중단 사유</dt><dd>{boundary.decision.stopReason ?? '없음'}</dd></div><div><dt>정책 제한 코드</dt><dd><code>{boundary.decision.restrictionCode ?? '없음'}</code></dd></div><div><dt>담당자 확인</dt><dd>{boundary.decision.underwriterRequired ? '필요' : '필요 없음'}</dd></div><div><dt>확인 시점</dt><dd>{formatDate(boundary.checkedAt)}</dd></div><div><dt>정책 버전</dt><dd><code>{boundary.policyVersion}</code></dd></div><div><dt>보정 버전</dt><dd><code>{boundary.calibrationVersion}</code></dd></div></dl></CustomerTechnicalDetails>
  </section>
}

function AssessmentPage() {
  const navigate = useNavigate()
  const { session, loading: sessionLoading } = useCustomerSession()
  const [result, setResult] = useState<AssessmentResponse | null>(null)
  const [boundaryResult, setBoundaryResult] = useState<PolicyBoundaryCheckResponse | null>(null)
  const [selectionResult, setSelectionResult] = useState<EvidenceSelectionResponse | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [errorStage, setErrorStage] = useState<ErrorStage | null>(null)
  const [phase, setPhase] = useState<Phase>('loading')
  const controllerRef = useRef<AbortController | null>(null)
  const sequenceRef = useRef(0)
  const busyRef = useRef(false)

  useEffect(() => { if (!sessionLoading && !session) navigate('/start', { replace: true }) }, [navigate, session, sessionLoading])

  const beginRequest = useCallback(() => {
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller
    return { controller, sequence: ++sequenceRef.current }
  }, [])

  const ensureSelection = useCallback(async (boundary: PolicyBoundaryCheckState, signal: AbortSignal) => {
    if (!session) throw new Error('session is required')
    let next = await evidenceSelectionProvider.get(session.sessionId, signal)
    validateSelection(next, boundary.boundaryCheckId, session.sessionId)
    if (!next.selection) {
      next = await withMinimumDuration(evidenceSelectionProvider.selectNext(session.sessionId, signal))
      validateSelection(next, boundary.boundaryCheckId, session.sessionId)
    }
    return next
  }, [session])

  const loadInitial = useCallback(async () => {
    if (!session || busyRef.current) return
    busyRef.current = true
    const { controller, sequence } = beginRequest()
    let stage: ErrorStage = 'load'
    setPhase('loading'); setError(null); setErrorStage(null)
    try {
      const next = await assessmentProvider.get({ sessionId: session.sessionId, profileType: session.selectedProfileType }, controller.signal)
      validateAssessment(next, session.sessionId)
      if (sequence !== sequenceRef.current) return
      setResult(next); setBoundaryResult(null); setSelectionResult(null)
      if (next.assessment.status === 'COMPLETED') {
        stage = 'boundary-load'
        setPhase('checking')
        const recoveredBoundary = await policyBoundaryProvider.get(session.sessionId, controller.signal)
        validateBoundary(recoveredBoundary, next.assessment, session.sessionId)
        if (sequence === sequenceRef.current) setBoundaryResult(recoveredBoundary)
        if (recoveredBoundary.boundaryCheck?.decision.status === 'AMBIGUOUS') {
          stage = 'selection'
          setPhase('selecting')
          const recoveredSelection = await ensureSelection(recoveredBoundary.boundaryCheck, controller.signal)
          if (sequence === sequenceRef.current) setSelectionResult(recoveredSelection)
        }
      }
    } catch (caught) {
      if (!controller.signal.aborted && sequence === sequenceRef.current) {
        setError(stage === 'selection' ? normalizeEvidenceSelectionError(caught) : stage === 'boundary-load' ? normalizePolicyBoundaryError(caught) : normalizeAssessmentError(caught))
        setErrorStage(stage)
      }
    } finally {
      if (sequence === sequenceRef.current) setPhase('idle')
      busyRef.current = false
    }
  }, [beginRequest, ensureSelection, session])

  const recoverBoundary = useCallback(async () => {
    if (!session || result?.assessment.status !== 'COMPLETED' || busyRef.current) return
    busyRef.current = true
    const { controller, sequence } = beginRequest()
    let stage: ErrorStage = 'boundary-load'
    setPhase('checking'); setError(null); setErrorStage(null); setSelectionResult(null)
    try {
      const recovered = await policyBoundaryProvider.get(session.sessionId, controller.signal)
      validateBoundary(recovered, result.assessment, session.sessionId)
      if (sequence === sequenceRef.current) setBoundaryResult(recovered)
      if (recovered.boundaryCheck?.decision.status === 'AMBIGUOUS') {
        stage = 'selection'
        setPhase('selecting')
        const recoveredSelection = await ensureSelection(recovered.boundaryCheck, controller.signal)
        if (sequence === sequenceRef.current) setSelectionResult(recoveredSelection)
      }
    } catch (caught) {
      if (!controller.signal.aborted && sequence === sequenceRef.current) { setError(stage === 'selection' ? normalizeEvidenceSelectionError(caught) : normalizePolicyBoundaryError(caught)); setErrorStage(stage) }
    } finally {
      if (sequence === sequenceRef.current) setPhase('idle')
      busyRef.current = false
    }
  }, [beginRequest, ensureSelection, result, session])

  const checkBoundary = useCallback(async () => {
    if (!session || result?.assessment.status !== 'COMPLETED' || busyRef.current) return
    busyRef.current = true
    const { controller, sequence } = beginRequest()
    let stage: ErrorStage = 'boundary-check'
    setPhase('checking'); setError(null); setErrorStage(null); setSelectionResult(null)
    try {
      const checked = await withMinimumDuration(policyBoundaryProvider.check(session.sessionId, controller.signal))
      validateBoundary(checked, result.assessment, session.sessionId)
      if (sequence === sequenceRef.current) setBoundaryResult(checked)
      if (checked.boundaryCheck?.decision.status === 'AMBIGUOUS') {
        stage = 'selection'
        setPhase('selecting')
        const nextSelection = await ensureSelection(checked.boundaryCheck, controller.signal)
        if (sequence === sequenceRef.current) setSelectionResult(nextSelection)
      }
    } catch (caught) {
      if (!controller.signal.aborted && sequence === sequenceRef.current) { setError(stage === 'selection' ? normalizeEvidenceSelectionError(caught) : normalizePolicyBoundaryError(caught)); setErrorStage(stage) }
    } finally {
      if (sequence === sequenceRef.current) setPhase('idle')
      busyRef.current = false
    }
  }, [beginRequest, ensureSelection, result, session])

  const recoverSelection = useCallback(async () => {
    const boundary = boundaryResult?.boundaryCheck
    if (!session || !boundary || boundary.decision.status !== 'AMBIGUOUS' || busyRef.current) return
    busyRef.current = true
    const { controller, sequence } = beginRequest()
    setPhase('selecting'); setError(null); setErrorStage(null)
    try {
      const nextSelection = await ensureSelection(boundary, controller.signal)
      if (sequence === sequenceRef.current) setSelectionResult(nextSelection)
    } catch (caught) {
      if (!controller.signal.aborted && sequence === sequenceRef.current) { setError(normalizeEvidenceSelectionError(caught)); setErrorStage('selection') }
    } finally {
      if (sequence === sequenceRef.current) setPhase('idle')
      busyRef.current = false
    }
  }, [beginRequest, boundaryResult, ensureSelection, session])

  const runAssessment = useCallback(async () => {
    if (!session || busyRef.current) return
    busyRef.current = true
    const { controller, sequence } = beginRequest()
    let stage: ErrorStage = 'run'
    setPhase('running'); setError(null); setErrorStage(null); setBoundaryResult(null); setSelectionResult(null)
    try {
      const next = await withMinimumDuration(assessmentProvider.run({ sessionId: session.sessionId, profileType: session.selectedProfileType }, controller.signal))
      validateAssessment(next, session.sessionId)
      if (sequence !== sequenceRef.current) return
      setResult(next)
      if (next.assessment.status === 'COMPLETED') {
        stage = 'boundary-check'
        setPhase('checking')
        const checked = await withMinimumDuration(policyBoundaryProvider.check(session.sessionId, controller.signal))
        validateBoundary(checked, next.assessment, session.sessionId)
        if (sequence === sequenceRef.current) setBoundaryResult(checked)
        if (checked.boundaryCheck?.decision.status === 'AMBIGUOUS') {
          stage = 'selection'
          setPhase('selecting')
          const nextSelection = await ensureSelection(checked.boundaryCheck, controller.signal)
          if (sequence === sequenceRef.current) setSelectionResult(nextSelection)
        }
      }
    } catch (caught) {
      if (!controller.signal.aborted && sequence === sequenceRef.current) {
        setError(stage === 'run' ? normalizeAssessmentError(caught) : stage === 'selection' ? normalizeEvidenceSelectionError(caught) : normalizePolicyBoundaryError(caught))
        setErrorStage(stage)
      }
    } finally {
      if (sequence === sequenceRef.current) setPhase('idle')
      busyRef.current = false
    }
  }, [beginRequest, ensureSelection, session])

  useEffect(() => {
    if (session) queueMicrotask(() => void loadInitial())
    return () => { sequenceRef.current += 1; controllerRef.current?.abort(); busyRef.current = false }
  }, [loadInitial, session])

  if (sessionLoading || !session) return null
  const state = result?.assessment
  const copy = state ? statusCopy[state.status] : null
  const boundary = boundaryResult?.boundaryCheck ?? null
  const selection = selectionResult?.selection ?? null
  const retry = errorStage === 'run' ? runAssessment : errorStage === 'boundary-check' ? checkBoundary : errorStage === 'boundary-load' ? recoverBoundary : errorStage === 'selection' ? recoverSelection : loadInitial
  const actionCopy = !state ? '기존 평가 상태를 불러오고 있습니다.'
    : state.status === 'NOT_RUN' ? '사용자가 확인을 선택하기 전에는 기존 은행 평가 결과를 불러오지 않습니다.'
      : state.status !== 'COMPLETED' ? '정책 경계는 은행의 기존 평가를 확인한 뒤 살펴볼 수 있습니다.'
        : !boundary ? '평가 결과에 따라 추가 자료가 필요한지 확인해주세요.'
          : boundary.decision.restrictionCode ? restrictedBoundaryCopy.description
            : boundaryCopy[boundary.decision.status].description

  return <div className="workspace-shell customer-flow"><Header /><main id="main-content" tabIndex={-1} className="assessment-page"><div className="container assessment-page__inner">
    <CustomerFlowSteps current="assessment" className="assessment-steps" />
    <header className="assessment-heading"><div><h1 className="page-title-lines"><span>은행의 기존 평가를 확인하고</span><span>필요한 추가 자료를 안내합니다</span></h1><p>기존 CB·선택적 SCB·은행 내부 평가 결과를 기준점으로 불러옵니다. CredAble이 새로운 신용점수를 만드는 단계가 아닙니다.</p></div><aside><span>사업자 유형</span><strong>{session.demoProfile.displayName}</strong><small>평가 주체와 사용 데이터가 이 유형에 맞게 적용됩니다.</small></aside></header>

    <div className="assessment-live" role="status" aria-live="polite">{phase === 'loading' ? '기존 평가 상태를 확인하고 있습니다.' : phase === 'running' ? '기존 은행 평가 결과를 불러오고 있습니다.' : phase === 'checking' ? '정책 경계를 확인하고 있습니다.' : phase === 'selecting' ? '부족한 정보를 보완할 최소 증빙을 선택하고 있습니다.' : error ? '요청을 완료하지 못했습니다.' : '현재 평가 상태를 확인했습니다.'}</div>
    {error && <section className="assessment-error" role="alert"><div><strong>{error.message}</strong><CustomerTechnicalDetails title="오류 기술 정보 보기"><dl><div><dt>오류 코드</dt><dd><code>{error.code}</code></dd></div>{error.requestId && <div><dt>요청 ID</dt><dd><code>{error.requestId}</code></dd></div>}</dl></CustomerTechnicalDetails></div>{error.retryable && <button type="button" onClick={() => void retry()}>{errorStage === 'selection' ? '요청 자료 다시 확인' : errorStage?.startsWith('boundary') ? '정책 경계 다시 확인' : '기존 평가 다시 확인'}</button>}</section>}
    {phase !== 'idle' && !result && <div className="assessment-skeleton" aria-hidden="true"><span /><span /></div>}

    {state && copy && <>
      <section className={`assessment-result assessment-result--${state.status.toLowerCase()}`} aria-labelledby="assessment-result-title"><div className="assessment-result__icon" aria-hidden="true">{copy.icon}</div><div><span>현재 평가 상태</span><h2 id="assessment-result-title">{copy.label}</h2><p className="assessment-result__description">{copy.description}</p></div></section>
      {state.status === 'INSUFFICIENT_DATA' && <p className="assessment-assurance">이 상태는 신용이 낮거나 대출 자격이 없다는 의미가 아닙니다.</p>}
      <div className="assessment-detail-grid"><UncertaintyPanel state={state} /></div>
      <CustomerTechnicalDetails><dl><div><dt>처리 상태</dt><dd><code>{state.status}</code></dd></div><div><dt>결과 계산 시점</dt><dd>{formatDate(state.calculatedAt)}</dd></div><div><dt>평가 ID</dt><dd><code>{state.assessmentId ?? '확인되지 않음'}</code></dd></div><div><dt>입력 데이터 묶음</dt><dd><code>{state.inputSnapshotId ?? '확인되지 않음'}</code></dd></div><div><dt>모델 버전</dt><dd><code>{state.modelVersion ?? '확인되지 않음'}</code></dd></div><div><dt>상태 코드</dt><dd><code>{state.reasonCode ?? '없음'}</code></dd></div></dl></CustomerTechnicalDetails>
      {boundary && <BoundaryPanel boundary={boundary} selection={selection} />}
      {boundary && <AssessmentExplanationPanel key={boundary.boundaryCheckId} sessionId={session.sessionId} />}
      {boundary && state.status === 'COMPLETED' && <AssessmentReviewPanel sessionId={session.sessionId} />}
    </>}

    <section className="assessment-actions"><div><strong>{boundary ? (boundary.decision.restrictionCode ? restrictedBoundaryCopy.label : boundaryCopy[boundary.decision.status].label) : state?.status === 'COMPLETED' ? '정책 경계를 확인해주세요' : '기존 평가 상태를 먼저 확인해주세요'}</strong><p>{actionCopy}</p>{boundary?.decision.status === 'STABLE' && <small>추가 자료 없이 자사 상품 조건을 확인할 수 있습니다.</small>}{boundary?.decision.status === 'AMBIGUOUS' && <small>요청 자료와 제출 버튼은 위 카드에서 바로 확인할 수 있습니다.</small>}</div><div><Link className="button button--secondary" to="/data-connection">연결 정보 확인</Link>{state?.status === 'NOT_RUN' && <button className="button button--primary" type="button" onClick={() => void runAssessment()} disabled={phase !== 'idle'}>기존 평가 결과 불러오기</button>}{state && state.status !== 'NOT_RUN' && state.status !== 'COMPLETED' && <button className="button button--secondary" type="button" onClick={() => void runAssessment()} disabled={phase !== 'idle'}>기존 평가 다시 확인</button>}{state?.status === 'COMPLETED' && !boundary && <button className="button button--primary" type="button" onClick={() => void checkBoundary()} disabled={phase !== 'idle'}>정책 경계 확인</button>}{boundary?.decision.status === 'STABLE' && <Link className="button button--primary" to="/products">자사 상품 조건 확인</Link>}</div></section>
  </div></main></div>
}

export default AssessmentPage
