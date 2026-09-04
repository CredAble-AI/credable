import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { normalizeDataConnectionError } from '../api/dataConnectionClient'
import Header from '../components/Header'
import { findDemoProfile } from '../data/demoProfiles'
import { customerSessionProvider } from '../mocks/customerSessionProvider'
import { mockDataConnectionProvider } from '../mocks/dataConnectionProvider'
import type { ApiError } from '../types/case'
import type { ConsentSourceType, DataConnectionRequest, DataConnectionResult, DataSourceState, RetrievalStatus, VerificationStatus } from '../types/dataConnection'
import './DataConnectionPage.css'

const provider = mockDataConnectionProvider
const presentation: Record<ConsentSourceType, { group: 'bank' | 'consented'; owner: string; purpose: string }> = {
  BANK_INTERNAL: { group: 'bank', owner: '이용 은행', purpose: '고객확인 및 계좌·대출 요약 확인' },
  CREDIT_INFORMATION: { group: 'bank', owner: '이용 은행 및 정식 조회기관', purpose: '정식 절차로 조회한 정보 확인' },
  CUSTOMER_SUBMITTED: { group: 'consented', owner: '고객 및 이용 은행', purpose: '고객이 선택한 소득·사업·재무 자료 확인' },
  EXTERNAL_CONNECTED: { group: 'consented', owner: '동의한 금융기관 또는 제휴사', purpose: '고객 동의와 제휴 범위 내 정보 확인' },
}
const retrievalLabel: Record<RetrievalStatus, string> = { CONSENT_REQUIRED: '선택하지 않음', NOT_REQUESTED: '조회 전', RETRIEVED: '연결됨', NO_DATA: '조회 가능한 데이터 없음', FAILED: '연결 실패' }
const verificationLabel: Record<VerificationStatus, string> = { NOT_STARTED: '검증 전', VERIFIED: '검증 완료', UNVERIFIED: '확인 필요', STALE: '오래된 데이터' }
const statusIcon: Record<RetrievalStatus, string> = { CONSENT_REQUIRED: '–', NOT_REQUESTED: '…', RETRIEVED: '✓', NO_DATA: '○', FAILED: '!' }
const formatDate = (value?: string | null) => value ? new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) : '확인되지 않음'

function SourceCard({ source, busy, error, onRetry }: { source: DataSourceState; busy: boolean; error?: ApiError; onRetry: () => void }) {
  const meta = presentation[source.sourceType]
  return <article className={`source-card source-card--${source.retrievalStatus.toLowerCase()}`}>
    <div className="source-card__top"><span className="source-card__icon" aria-hidden="true">{statusIcon[source.retrievalStatus]}</span><div><span className="source-card__scope">{meta.group === 'bank' ? '은행 보유 · 필수' : '고객 동의 기반 · 선택'}</span><h3>{source.displayName}</h3></div></div>
    <div className="status-row"><span>{retrievalLabel[source.retrievalStatus]}</span><span>{verificationLabel[source.verificationStatus]}</span><span>Mock · Demo</span></div>
    <dl><div><dt>보유·제공 주체</dt><dd>{meta.owner}</dd></div><div><dt>이용 목적</dt><dd>{meta.purpose}</dd></div><div><dt>출처</dt><dd>{source.displayName}</dd></div><div><dt>데이터 기준시점</dt><dd>{formatDate(source.observedAt)}</dd></div><div><dt>시스템 조회시점</dt><dd>{formatDate(source.retrievedAt)}</dd></div></dl>
    {source.reasonCode && <p className="source-card__reason">상태 코드: <span>{source.reasonCode}</span></p>}
    {error && <p className="source-card__error" role="alert">{error.message}{error.requestId ? <small>Request ID: {error.requestId}</small> : null}</p>}
    {source.retrievalStatus === 'FAILED' && provider.retrySource && <button className="retry-button" type="button" onClick={onRetry} disabled={busy}>{busy ? '이 항목 재시도 중…' : `${source.displayName} 다시 연결`}</button>}
  </article>
}

function DataConnectionPage() {
  const navigate = useNavigate()
  const [session] = useState(() => customerSessionProvider.get())
  const [result, setResult] = useState<DataConnectionResult | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [itemErrors, setItemErrors] = useState<Partial<Record<ConsentSourceType, ApiError>>>({})
  const [isLoading, setIsLoading] = useState(true)
  const [retrying, setRetrying] = useState<ConsentSourceType | null>(null)
  const requestSequence = useRef(0)
  const controllerRef = useRef<AbortController | null>(null)
  const requiredComplete = session ? Object.values(session.consents.required).every(Boolean) : false
  const requestRef = useRef<DataConnectionRequest | null>(session ? { sessionId: session.sessionId, profileType: session.selectedProfileType, consents: session.consents } : null)

  useEffect(() => {
    if (!session) navigate('/start', { replace: true })
    else if (!requiredComplete) navigate('/consent', { replace: true })
  }, [navigate, requiredComplete, session])

  const load = useCallback(async (refresh = false) => {
    const request = requestRef.current
    if (!request || !requiredComplete) return
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller
    const sequence = ++requestSequence.current
    setIsLoading(true)
    setError(null)
    try {
      const next = await (refresh ? provider.refresh(request, controller.signal) : provider.list(request, controller.signal))
      if (sequence === requestSequence.current) setResult(next)
    } catch (caught) {
      if (!controller.signal.aborted && sequence === requestSequence.current) setError(normalizeDataConnectionError(caught))
    } finally {
      if (sequence === requestSequence.current) setIsLoading(false)
    }
  }, [requiredComplete])

  useEffect(() => {
    if (requestRef.current && requiredComplete) void load()
    return () => controllerRef.current?.abort()
  }, [load, requiredComplete])

  const retrySource = async (sourceType: ConsentSourceType) => {
    const request = requestRef.current
    if (!request || !provider.retrySource || retrying) return
    const controller = new AbortController()
    controllerRef.current = controller
    setRetrying(sourceType)
    setItemErrors((current) => ({ ...current, [sourceType]: undefined }))
    try {
      const source = await provider.retrySource(request, sourceType, controller.signal)
      setResult((current) => current ? { ...current, dataSources: current.dataSources.map((item) => item.sourceType === sourceType ? source : item) } : current)
    } catch (caught) {
      if (!controller.signal.aborted) setItemErrors((current) => ({ ...current, [sourceType]: normalizeDataConnectionError(caught) }))
    } finally {
      if (!controller.signal.aborted) setRetrying(null)
    }
  }

  if (!session || !requiredComplete) return null
  const bankSources = result?.dataSources.filter((source) => presentation[source.sourceType].group === 'bank') ?? []
  const consentedSources = result?.dataSources.filter((source) => presentation[source.sourceType].group === 'consented') ?? []
  return <div className="workspace-shell customer-flow"><Header /><main className="connection-page"><div className="container connection-page__inner">
    <nav className="flow-steps" aria-label="진행 단계"><span>시작</span><span>동의</span><strong aria-current="step">데이터 연결</strong><span>보완 평가</span><span>상품 비교</span></nav>
    <header className="connection-heading"><div><span className="connection-badge">Mock mode · Demo Only</span><p className="flow-kicker">DATA CONNECTION</p><h1>보완 평가에 사용할 데이터를 확인합니다</h1><p>은행 보유 데이터와 고객이 동의한 데이터의 연결·검증 상태를 확인합니다. 데이터가 없거나 연결되지 않았다는 이유만으로 신용이 불리하게 판단되지는 않습니다.</p></div><aside><span>현재 Demo 프로필</span><strong>{findDemoProfile(session.selectedProfileType)?.name}</strong><small>대표 합성 사례이며 이용 대상을 제한하지 않습니다.</small></aside></header>
    <div className="connection-status" aria-live="polite" role="status">{isLoading ? '데이터 연결·검증 상태를 확인하고 있습니다.' : retrying ? `${result?.dataSources.find((item) => item.sourceType === retrying)?.displayName} 항목을 다시 확인하고 있습니다.` : '현재 데이터 상태를 확인했습니다.'}</div>
    {error && <section className="connection-error" role="alert"><div><strong>{error.message}</strong><small>오류 코드: {error.code}{error.requestId ? ` · Request ID: ${error.requestId}` : ''}</small></div>{error.retryable && <button type="button" onClick={() => void load()}>다시 확인</button>}</section>}
    {isLoading && !result && <div className="source-skeletons" aria-hidden="true"><span /><span /><span /></div>}
    {!isLoading && !error && result?.dataSources.length === 0 && <section className="empty-sources"><h2>표시할 데이터 출처가 없습니다</h2><p>현재 세션에서 확인 가능한 데이터 출처가 반환되지 않았습니다.</p></section>}
    {result && result.dataSources.length > 0 && <><section className="source-section" aria-labelledby="bank-source-title"><div className="source-section__heading"><div><span>01</span><h2 id="bank-source-title">은행 보유 데이터</h2></div><p>은행이 보유하거나 정식 절차로 조회한 요약 상태입니다.</p></div><div className="source-grid">{bankSources.map((source) => <SourceCard key={source.sourceType} source={source} busy={retrying === source.sourceType} error={itemErrors[source.sourceType]} onRetry={() => void retrySource(source.sourceType)} />)}</div></section><section className="source-section" aria-labelledby="consented-source-title"><div className="source-section__heading"><div><span>02</span><h2 id="consented-source-title">고객 동의 기반 데이터</h2></div><p>선택하지 않은 항목은 연결 실패가 아니라 ‘선택하지 않음’으로 표시합니다.</p></div><div className="source-grid">{consentedSources.map((source) => <SourceCard key={source.sourceType} source={source} busy={retrying === source.sourceType} error={itemErrors[source.sourceType]} onRetry={() => void retrySource(source.sourceType)} />)}</div></section></>}
    <section className="connection-actions" aria-label="데이터 연결 다음 작업"><div><strong>{result?.canProceed ? '다음 단계로 진행할 수 있습니다' : '현재 다음 단계로 진행할 수 없습니다'}</strong><p>{result?.proceedReason ?? '데이터 상태 응답을 기다리고 있습니다.'}</p></div><div className="connection-actions__buttons"><Link className="button button--secondary" to="/consent">동의 범위 확인</Link><button className="button button--secondary" type="button" onClick={() => void load(true)} disabled={isLoading || Boolean(retrying)}>전체 상태 다시 확인</button>{result?.canProceed && <Link className="button button--primary" to="/assessment">보완 평가 결과 확인</Link>}</div></section>
  </div></main></div>
}

export default DataConnectionPage
