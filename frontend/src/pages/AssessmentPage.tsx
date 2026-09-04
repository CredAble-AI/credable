import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { normalizeAssessmentError } from '../api/assessmentClient'
import Header from '../components/Header'
import { findDemoProfile } from '../data/demoProfiles'
import { mockAssessmentProvider } from '../mocks/assessmentProvider'
import { customerSessionProvider } from '../mocks/customerSessionProvider'
import { mockDataConnectionProvider } from '../mocks/dataConnectionProvider'
import type { AssessmentRequest, AssessmentResult, AssessmentStatus } from '../types/assessment'
import type { ApiError } from '../types/case'
import './AssessmentPage.css'

const provider = mockAssessmentProvider
const statusCopy: Record<AssessmentStatus, { label: string; icon: string }> = {
  NOT_RUN: { label: '평가 준비 중', icon: '…' },
  MODEL_NOT_CONFIGURED: { label: '평가 방식 미구성', icon: '○' },
  COMPLETED: { label: '평가 완료', icon: '✓' },
  INSUFFICIENT_DATA: { label: '데이터 부족', icon: 'i' },
  UNSUPPORTED_CUSTOMER_TYPE: { label: '지원되지 않는 고객 유형', icon: '–' },
  FAILED: { label: '평가 오류', icon: '!' },
}
const formatDate = (value?: string | null) => value ? new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) : '확인되지 않음'

function AssessmentPage() {
  const navigate = useNavigate()
  const [session] = useState(() => customerSessionProvider.get())
  const [result, setResult] = useState<AssessmentResult | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [phase, setPhase] = useState<'loading' | 'running' | 'idle'>('loading')
  const controllerRef = useRef<AbortController | null>(null)
  const requestSequence = useRef(0)
  const requiredComplete = session ? Object.values(session.consents.required).every(Boolean) : false
  const requestRef = useRef<AssessmentRequest | null>(session ? { sessionId: session.sessionId, profileType: session.selectedProfileType } : null)
  const connectionRequestRef = useRef(session ? { sessionId: session.sessionId, profileType: session.selectedProfileType, consents: session.consents } : null)

  useEffect(() => {
    if (!session) navigate('/start', { replace: true })
    else if (!requiredComplete) navigate('/consent', { replace: true })
  }, [navigate, requiredComplete, session])

  const load = useCallback(async (forceRun = false) => {
    const request = requestRef.current
    if (!request || !requiredComplete || phase === 'running') return
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller
    const sequence = ++requestSequence.current
    setError(null)
    setPhase(forceRun ? 'running' : 'loading')
    try {
      const connection = connectionRequestRef.current
      if (!connection) return
      let readiness
      try {
        readiness = await mockDataConnectionProvider.list(connection, controller.signal)
      } catch {
        if (!controller.signal.aborted) navigate('/data-connection', { replace: true })
        return
      }
      if (readiness.canProceed !== true) {
        navigate('/data-connection', { replace: true })
        return
      }
      let next = forceRun ? await provider.run(request, controller.signal) : await provider.get(request, controller.signal)
      if (next.sessionId !== request.sessionId) throw { code: 'ASSESSMENT_SESSION_MISMATCH', message: '현재 세션의 평가 결과를 확인할 수 없습니다.', retryable: true } satisfies ApiError
      if (!forceRun && next.assessment.status === 'NOT_RUN') {
        if (sequence === requestSequence.current) setPhase('running')
        next = await provider.run(request, controller.signal)
      }
      if (next.sessionId !== request.sessionId) throw { code: 'ASSESSMENT_SESSION_MISMATCH', message: '현재 세션의 평가 결과를 확인할 수 없습니다.', retryable: true } satisfies ApiError
      if (sequence === requestSequence.current) setResult(next)
    } catch (caught) {
      if (!controller.signal.aborted && sequence === requestSequence.current) setError(normalizeAssessmentError(caught))
    } finally {
      if (sequence === requestSequence.current) setPhase('idle')
    }
  }, [navigate, phase, requiredComplete])

  useEffect(() => {
    if (requestRef.current && requiredComplete) void load()
    return () => controllerRef.current?.abort()
    // Run once for the fixed session snapshot on this visit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  if (!session || !requiredComplete) return null
  const state = result?.assessment
  const copy = state ? statusCopy[state.status] : null
  const incomplete = state && state.status !== 'COMPLETED'

  return <div className="workspace-shell customer-flow"><Header /><main className="assessment-page"><div className="container assessment-page__inner">
    <nav className="assessment-steps" aria-label="진행 단계"><span>시작</span><span>동의</span><span>데이터 연결</span><strong aria-current="step">보완 평가</strong><span>상품 비교</span></nav>
    <header className="assessment-heading"><div><span className="assessment-badge">Mock result · Demo Only</span><p className="flow-kicker">COMPLEMENTARY ASSESSMENT</p><h1>연결된 데이터를 바탕으로 보완 평가를 확인합니다</h1><p>은행이 승인한 데이터와 평가 방식으로 생성된 결과를 보여줍니다. 외부 신용점수를 직접 변경하거나 대출 승인을 확정하는 결과가 아닙니다.</p></div><aside><span>현재 Demo 프로필</span><strong>{findDemoProfile(session.selectedProfileType)?.name}</strong><small>프로필별 Demo 평가 방식은 서로 독립적입니다.</small></aside></header>

    <div className="assessment-live" role="status" aria-live="polite">{phase === 'loading' ? '기존 보완 평가 결과를 확인하고 있습니다.' : phase === 'running' ? '보완 평가를 실행하고 있습니다.' : error ? '보완 평가를 확인하지 못했습니다.' : '보완 평가 상태를 확인했습니다.'}</div>
    {error && <section className="assessment-error" role="alert"><div><strong>{error.message}</strong><small>오류 코드: {error.code}{error.requestId ? ` · Request ID: ${error.requestId}` : ''}</small></div>{error.retryable && <button type="button" onClick={() => void load()}>평가 다시 확인</button>}</section>}
    {phase !== 'idle' && !result && <div className="assessment-skeleton" aria-hidden="true"><span /><span /></div>}

    {state && copy && <>
      <section className={`assessment-result assessment-result--${state.status.toLowerCase()}`} aria-labelledby="assessment-result-title"><div className="assessment-result__icon" aria-hidden="true">{copy.icon}</div><div><span>{copy.label}</span><h2 id="assessment-result-title">{result.summary ?? '구조화된 평가 요약이 제공되지 않았습니다.'}</h2>{incomplete && <p>{result.proceedReason}</p>}</div></section>
      {state.status === 'INSUFFICIENT_DATA' && <p className="assessment-assurance">이는 신용이 낮거나 대출 자격이 없다는 의미가 아닙니다.</p>}
      {state.status === 'MODEL_NOT_CONFIGURED' && <p className="assessment-assurance">현재 Demo 환경에는 이 고객 유형의 평가 방식이 구성되지 않았습니다.</p>}
      <div className="assessment-detail-grid">
        <section className="assessment-panel" aria-labelledby="data-summary-title"><h2 id="data-summary-title">사용된 데이터 범위</h2>{result.dataSummary.length ? <ul>{result.dataSummary.map((item) => <li key={item}>{item}</li>)}</ul> : <p>제공된 비민감 데이터 요약이 없습니다.</p>}{result.excludedData.length > 0 && <><h3>제외 또는 확인되지 않은 데이터</h3><ul>{result.excludedData.map((item) => <li key={item}>{item}</li>)}</ul></>}</section>
        <section className="assessment-panel" aria-labelledby="metadata-title"><h2 id="metadata-title">평가 메타데이터</h2><dl><div><dt>처리 상태</dt><dd>{copy.label}</dd></div><div><dt>결과 계산 시점</dt><dd>{formatDate(state.calculatedAt)}</dd></div><div><dt>입력 Snapshot</dt><dd>{state.inputSnapshotId ?? '확인되지 않음'}</dd></div><div><dt>모델 버전</dt><dd>{state.modelVersion ?? '확인되지 않음'}</dd></div><div><dt>상태 코드</dt><dd>{state.reasonCode ?? '없음'}</dd></div><div><dt>결과 구분</dt><dd>{result.resultMode === 'MOCK' ? 'Mock · Demo Only' : 'Backend result'}</dd></div></dl></section>
      </div>
    </>}

    <section className="assessment-actions"><div><strong>{result?.canProceed ? '상품 조건 비교 단계로 이동할 수 있습니다' : '현재 평가 상태를 먼저 확인해주세요'}</strong><p>{result?.proceedReason ?? '평가 응답을 기다리고 있습니다.'}</p></div><div><Link className="button button--secondary" to="/data-connection">데이터 연결 상태 다시 확인</Link>{state && state.status !== 'COMPLETED' && <button className="button button--secondary" type="button" onClick={() => void load(true)} disabled={phase !== 'idle'}>평가 다시 확인</button>}{result?.canProceed && <Link className="button button--primary" to="/products">자사 대출상품 비교하기</Link>}</div></section>
  </div></main></div>
}

export default AssessmentPage
