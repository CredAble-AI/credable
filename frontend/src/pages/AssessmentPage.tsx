import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { normalizeAssessmentError } from '../api/assessmentClient'
import { normalizePolicyBoundaryError } from '../api/policyBoundaryClient'
import Header from '../components/Header'
import { isMockMode } from '../config/providerMode'
import { assessmentProvider, policyBoundaryProvider } from '../hooks/useAssessmentState'
import { useCustomerSession } from '../hooks/useCustomerSession'
import type { ApiError } from '../types/api'
import type { AssessmentResponse, AssessmentState, AssessmentStatus } from '../types/assessment'
import type { BoundaryStatus, PolicyBoundaryCheckResponse, PolicyBoundaryCheckState } from '../types/policyBoundary'
import './AssessmentPage.css'

type Phase = 'loading' | 'running' | 'checking' | 'idle'
type ErrorStage = 'load' | 'run' | 'boundary-load' | 'boundary-check'

const statusCopy: Record<AssessmentStatus, { label: string; icon: string; description: string }> = {
  NOT_RUN: { label: '기준평가 전', icon: '…', description: '아직 기준평가를 실행하지 않았습니다. 사용자가 실행을 선택하면 현재 데이터 Snapshot을 기준으로 평가합니다.' },
  MODEL_NOT_CONFIGURED: { label: '평가 방식 미구성', icon: '○', description: '현재 환경에는 이 사업자 유형의 평가 방식이 구성되지 않았습니다.' },
  COMPLETED: { label: '기준평가 완료', icon: '✓', description: '서버가 확정한 기준평가 상태와 가능한 평가 범위를 표시합니다.' },
  INSUFFICIENT_DATA: { label: '현재 데이터로 산출 불가', icon: 'i', description: '확인된 데이터만으로는 현재 기준평가를 완료할 수 없습니다.' },
  UNSUPPORTED_CUSTOMER_TYPE: { label: '지원 대상 확인 필요', icon: '–', description: '현재 기준평가가 지원하지 않는 사업자 유형입니다.' },
  FAILED: { label: '기준평가 처리 실패', icon: '!', description: '기준평가 처리 중 오류가 발생했습니다. 상태 코드를 확인한 뒤 다시 실행할 수 있습니다.' },
}

const boundaryCopy: Record<BoundaryStatus, { label: string; description: string }> = {
  STABLE: { label: '단일 경로 확인', description: '서버가 가능한 경로를 하나로 확인했습니다. 추가 Evidence 확인은 필요하지 않습니다.' },
  AMBIGUOUS: { label: '추가 확인 필요', description: '서버가 여러 가능한 경로를 반환했습니다. 다음 Evidence 단계에서 필요한 증빙을 확인합니다.' },
  POLICY_BLOCKED: { label: '자동 처리 중단', description: '정책 경계 확인 결과 자동 처리가 중단되었습니다. 서버 응답에 따라 심사역 확인이 필요할 수 있습니다.' },
}

const formatDate = (value: string | null) => value
  ? new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
  : '확인되지 않음'
const formatValue = (value: number | null) => value == null ? '제공되지 않음' : new Intl.NumberFormat('ko-KR').format(value)

const validateAssessment = (result: AssessmentResponse, sessionId: string) => {
  if (result.sessionId !== sessionId) throw {
    code: 'ASSESSMENT_SESSION_MISMATCH',
    message: '현재 세션의 기준평가 결과를 확인할 수 없습니다.',
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
    message: '현재 기준평가와 일치하는 정책 경계 결과를 확인할 수 없습니다.',
    retryable: true,
  } satisfies ApiError
}

function UncertaintyPanel({ state }: { state: AssessmentState }) {
  const uncertainty = state.uncertainty
  if (!uncertainty) return null
  return <section className="assessment-panel assessment-uncertainty" aria-labelledby="uncertainty-title">
    <div className="assessment-panel__heading"><div><span>SERVER RESULT</span><h2 id="uncertainty-title">가능한 평가 범위</h2></div><span className="demo-chip">Demo Only</span></div>
    <p>아래 값은 서버가 반환한 불확실성 범위입니다. Demo 등급 표시는 실제 CB 신용등급, 승인등급 또는 승인 가능성을 뜻하지 않습니다.</p>
    <div className="assessment-grade-set" aria-label="가능한 Demo 평가 범위">{uncertainty.gradeSet.length > 0 ? uncertainty.gradeSet.map((grade) => <code key={grade}>{grade}</code>) : <span>등급 범위가 제공되지 않았습니다.</span>}</div>
    <dl>
      <div><dt>모델 추정값</dt><dd>{formatValue(uncertainty.pointEstimate)}</dd></div>
      <div><dt>추정 범위</dt><dd>{uncertainty.lowerBound == null && uncertainty.upperBound == null ? '제공되지 않음' : `${formatValue(uncertainty.lowerBound)} ~ ${formatValue(uncertainty.upperBound)}`}</dd></div>
      <div><dt>보정 방식</dt><dd>{uncertainty.calibrationMode}</dd></div>
      <div><dt>보정 버전</dt><dd>{uncertainty.calibrationVersion}</dd></div>
    </dl>
  </section>
}

function BoundaryPanel({ boundary }: { boundary: PolicyBoundaryCheckState }) {
  const copy = boundaryCopy[boundary.decision.status]
  return <section className={`assessment-boundary assessment-boundary--${boundary.decision.status.toLowerCase()}`} aria-labelledby="boundary-title">
    <div className="assessment-panel__heading"><div><span>POLICY BOUNDARY</span><h2 id="boundary-title">{copy.label}</h2></div><span className="assessment-boundary__status">{boundary.decision.status}</span></div>
    <p>{copy.description}</p>
    <div className="assessment-boundary__lists">
      <div><h3>서버가 반환한 가능 경로</h3>{boundary.decision.possibleRoutes.length > 0 ? <ul>{boundary.decision.possibleRoutes.map((route) => <li key={route}><code>{route}</code></li>)}</ul> : <p>가능 경로가 제공되지 않았습니다.</p>}</div>
      <div><h3>교차한 정책 경계</h3>{boundary.decision.crossedBoundaryCodes.length > 0 ? <ul>{boundary.decision.crossedBoundaryCodes.map((code) => <li key={code}><code>{code}</code></li>)}</ul> : <p>교차한 경계 코드가 없습니다.</p>}</div>
    </div>
    <dl>
      <div><dt>자동 처리 중단 사유</dt><dd>{boundary.decision.stopReason ?? '없음'}</dd></div>
      <div><dt>심사역 확인</dt><dd>{boundary.decision.underwriterRequired ? '필요' : '서버 응답상 필요 없음'}</dd></div>
      <div><dt>확인 시점</dt><dd>{formatDate(boundary.checkedAt)}</dd></div>
      <div><dt>정책 버전</dt><dd>{boundary.policyVersion}</dd></div>
      <div><dt>보정 버전</dt><dd>{boundary.calibrationVersion}</dd></div>
    </dl>
  </section>
}

function AssessmentPage() {
  const navigate = useNavigate()
  const { session, loading: sessionLoading } = useCustomerSession()
  const [result, setResult] = useState<AssessmentResponse | null>(null)
  const [boundaryResult, setBoundaryResult] = useState<PolicyBoundaryCheckResponse | null>(null)
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
      setResult(next); setBoundaryResult(null)
      if (next.assessment.status === 'COMPLETED') {
        stage = 'boundary-load'
        setPhase('checking')
        const recoveredBoundary = await policyBoundaryProvider.get(session.sessionId, controller.signal)
        validateBoundary(recoveredBoundary, next.assessment, session.sessionId)
        if (sequence === sequenceRef.current) setBoundaryResult(recoveredBoundary)
      }
    } catch (caught) {
      if (!controller.signal.aborted && sequence === sequenceRef.current) {
        setError(stage === 'boundary-load' ? normalizePolicyBoundaryError(caught) : normalizeAssessmentError(caught))
        setErrorStage(stage)
      }
    } finally {
      if (sequence === sequenceRef.current) setPhase('idle')
      busyRef.current = false
    }
  }, [beginRequest, session])

  const recoverBoundary = useCallback(async () => {
    if (!session || result?.assessment.status !== 'COMPLETED' || busyRef.current) return
    busyRef.current = true
    const { controller, sequence } = beginRequest()
    setPhase('checking'); setError(null); setErrorStage(null)
    try {
      const recovered = await policyBoundaryProvider.get(session.sessionId, controller.signal)
      validateBoundary(recovered, result.assessment, session.sessionId)
      if (sequence === sequenceRef.current) setBoundaryResult(recovered)
    } catch (caught) {
      if (!controller.signal.aborted && sequence === sequenceRef.current) { setError(normalizePolicyBoundaryError(caught)); setErrorStage('boundary-load') }
    } finally {
      if (sequence === sequenceRef.current) setPhase('idle')
      busyRef.current = false
    }
  }, [beginRequest, result, session])

  const checkBoundary = useCallback(async () => {
    if (!session || result?.assessment.status !== 'COMPLETED' || busyRef.current) return
    busyRef.current = true
    const { controller, sequence } = beginRequest()
    setPhase('checking'); setError(null); setErrorStage(null)
    try {
      const checked = await policyBoundaryProvider.check(session.sessionId, controller.signal)
      validateBoundary(checked, result.assessment, session.sessionId)
      if (sequence === sequenceRef.current) setBoundaryResult(checked)
    } catch (caught) {
      if (!controller.signal.aborted && sequence === sequenceRef.current) { setError(normalizePolicyBoundaryError(caught)); setErrorStage('boundary-check') }
    } finally {
      if (sequence === sequenceRef.current) setPhase('idle')
      busyRef.current = false
    }
  }, [beginRequest, result, session])

  const runAssessment = useCallback(async () => {
    if (!session || busyRef.current) return
    busyRef.current = true
    const { controller, sequence } = beginRequest()
    let stage: ErrorStage = 'run'
    setPhase('running'); setError(null); setErrorStage(null); setBoundaryResult(null)
    try {
      const next = await assessmentProvider.run({ sessionId: session.sessionId, profileType: session.selectedProfileType }, controller.signal)
      validateAssessment(next, session.sessionId)
      if (sequence !== sequenceRef.current) return
      setResult(next)
      if (next.assessment.status === 'COMPLETED') {
        stage = 'boundary-check'
        setPhase('checking')
        const checked = await policyBoundaryProvider.check(session.sessionId, controller.signal)
        validateBoundary(checked, next.assessment, session.sessionId)
        if (sequence === sequenceRef.current) setBoundaryResult(checked)
      }
    } catch (caught) {
      if (!controller.signal.aborted && sequence === sequenceRef.current) {
        setError(stage === 'run' ? normalizeAssessmentError(caught) : normalizePolicyBoundaryError(caught))
        setErrorStage(stage)
      }
    } finally {
      if (sequence === sequenceRef.current) setPhase('idle')
      busyRef.current = false
    }
  }, [beginRequest, session])

  useEffect(() => {
    if (session) queueMicrotask(() => void loadInitial())
    return () => { sequenceRef.current += 1; controllerRef.current?.abort(); busyRef.current = false }
  }, [loadInitial, session])

  if (sessionLoading || !session) return null
  const state = result?.assessment
  const copy = state ? statusCopy[state.status] : null
  const boundary = boundaryResult?.boundaryCheck ?? null
  const retry = errorStage === 'run' ? runAssessment : errorStage === 'boundary-check' ? checkBoundary : errorStage === 'boundary-load' ? recoverBoundary : loadInitial
  const actionCopy = !state ? '기준평가 상태를 불러오고 있습니다.'
    : state.status === 'NOT_RUN' ? '사용자가 실행을 선택하기 전에는 기준평가를 자동으로 시작하지 않습니다.'
      : state.status !== 'COMPLETED' ? '정책 경계 확인은 완료된 기준평가에서만 진행됩니다.'
        : !boundary ? '저장된 정책 경계 결과가 없습니다. 확인을 선택하면 서버에 새 확인을 요청합니다.'
          : boundaryCopy[boundary.decision.status].description

  return <div className="workspace-shell customer-flow"><Header /><main id="main-content" tabIndex={-1} className="assessment-page"><div className="container assessment-page__inner">
    <nav className="assessment-steps" aria-label="진행 단계"><span>시작</span><span>동의</span><span>데이터 연결</span><strong aria-current="step">기준평가</strong><span>상품 비교</span></nav>
    <header className="assessment-heading"><div>{isMockMode && <span className="assessment-badge">Mock result · Demo Only</span>}<p className="flow-kicker">BASELINE ASSESSMENT</p><h1>연결된 데이터를 바탕으로 기준평가를 확인합니다</h1><p>서버가 확정한 평가 상태와 불확실성 범위를 그대로 보여줍니다. 프론트엔드는 적격성, 위험도, 정책 경로 또는 대출 조건을 다시 계산하지 않습니다.</p></div><aside><span>현재 Demo 사례</span><strong>{session.demoProfile.displayName}</strong><small>{session.demoProfile.description}</small></aside></header>

    <div className="assessment-live" role="status" aria-live="polite">{phase === 'loading' ? '저장된 기준평가 상태를 확인하고 있습니다.' : phase === 'running' ? '기준평가를 실행하고 있습니다.' : phase === 'checking' ? '정책 경계 상태를 확인하고 있습니다.' : error ? '요청을 완료하지 못했습니다.' : '서버 상태를 확인했습니다.'}</div>
    {error && <section className="assessment-error" role="alert"><div><strong>{error.message}</strong><small>오류 코드: {error.code}{error.requestId ? ` · Request ID: ${error.requestId}` : ''}</small></div>{error.retryable && <button type="button" onClick={() => void retry()}>{errorStage?.startsWith('boundary') ? '정책 경계 다시 확인' : '기준평가 다시 확인'}</button>}</section>}
    {phase !== 'idle' && !result && <div className="assessment-skeleton" aria-hidden="true"><span /><span /></div>}

    {state && copy && <>
      <section className={`assessment-result assessment-result--${state.status.toLowerCase()}`} aria-labelledby="assessment-result-title"><div className="assessment-result__icon" aria-hidden="true">{copy.icon}</div><div><span>{copy.label}</span><h2 id="assessment-result-title">{copy.description}</h2>{state.reasonCode && <p>서버 상태 코드 <code>{state.reasonCode}</code></p>}</div></section>
      {state.status === 'INSUFFICIENT_DATA' && <p className="assessment-assurance">이 상태는 신용이 낮거나 대출 자격이 없다는 의미가 아닙니다.</p>}
      <div className="assessment-detail-grid">
        <UncertaintyPanel state={state} />
        <section className="assessment-panel" aria-labelledby="metadata-title"><div className="assessment-panel__heading"><div><span>TRACEABILITY</span><h2 id="metadata-title">평가 메타데이터</h2></div><span className="demo-chip">Demo Only</span></div><dl><div><dt>처리 상태</dt><dd>{state.status}</dd></div><div><dt>결과 계산 시점</dt><dd>{formatDate(state.calculatedAt)}</dd></div><div><dt>평가 ID</dt><dd>{state.assessmentId ?? '확인되지 않음'}</dd></div><div><dt>입력 Snapshot</dt><dd>{state.inputSnapshotId ?? '확인되지 않음'}</dd></div><div><dt>모델 버전</dt><dd>{state.modelVersion ?? '확인되지 않음'}</dd></div><div><dt>상태 코드</dt><dd>{state.reasonCode ?? '없음'}</dd></div></dl></section>
      </div>
      {boundary && <BoundaryPanel boundary={boundary} />}
    </>}

    <section className="assessment-actions"><div><strong>{boundary ? boundaryCopy[boundary.decision.status].label : state?.status === 'COMPLETED' ? '정책 경계 상태를 확인해주세요' : '기준평가 상태를 먼저 확인해주세요'}</strong><p>{actionCopy}</p>{boundary?.decision.status === 'STABLE' && <small>다음 결과 화면은 후속 흐름이 확정되면 연결합니다.</small>}</div><div><Link className="button button--secondary" to="/data-connection">데이터 연결 상태 확인</Link>{state?.status === 'NOT_RUN' && <button className="button button--primary" type="button" onClick={() => void runAssessment()} disabled={phase !== 'idle'}>기준평가 실행</button>}{state && state.status !== 'NOT_RUN' && state.status !== 'COMPLETED' && <button className="button button--secondary" type="button" onClick={() => void runAssessment()} disabled={phase !== 'idle'}>기준평가 다시 실행</button>}{state?.status === 'COMPLETED' && !boundary && <button className="button button--primary" type="button" onClick={() => void checkBoundary()} disabled={phase !== 'idle'}>정책 경계 확인</button>}{boundary?.decision.status === 'AMBIGUOUS' && <Link className="button button--primary" to="/evidence">다음 Evidence 확인</Link>}</div></section>
  </div></main></div>
}

export default AssessmentPage
