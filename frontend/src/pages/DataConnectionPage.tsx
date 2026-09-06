import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { normalizeDataConnectionError } from '../api/dataConnectionClient'
import CustomerFlowSteps from '../components/CustomerFlowSteps'
import Header from '../components/Header'
import CustomerTechnicalDetails from '../components/CustomerTechnicalDetails'
import { useCustomerSession } from '../hooks/useCustomerSession'
import { dataConnectionProvider } from '../hooks/useDataConnectionState'
import type { ApiError } from '../types/api'
import type { ConsentSourceType, DataSourceListResponse, DataSourceState, RetrievalStatus, VerificationStatus } from '../types/dataConnection'
import './DataConnectionPage.css'

const retrievalLabel: Record<RetrievalStatus, string> = {
  CONSENT_REQUIRED: '동의 필요',
  NOT_REQUESTED: '조회 전',
  RETRIEVED: '조회 완료',
  NO_DATA: '조회 가능한 데이터 없음',
  FAILED: '조회 실패',
}
const verificationLabel: Record<VerificationStatus, string> = {
  NOT_STARTED: '검증 전',
  VERIFIED: '검증 완료',
  UNVERIFIED: '확인 필요',
  STALE: '기준시점 확인 필요',
}
const statusIcon: Record<RetrievalStatus, string> = {
  CONSENT_REQUIRED: '–',
  NOT_REQUESTED: '…',
  RETRIEVED: '✓',
  NO_DATA: '○',
  FAILED: '!',
}
const baselineSourceTypes: ConsentSourceType[] = ['BANK_INTERNAL', 'CREDIT_INFORMATION']
const sourcePurpose: Record<ConsentSourceType, string> = {
  BANK_INTERNAL: '기존 대출·상환·연체·거래 이력과 은행 보유 평가',
  CREDIT_INFORMATION: '신용평가사에서 조회한 사업자 신용정보',
  CUSTOMER_SUBMITTED: '불확실성이 남을 때 요청하는 고객 제출 자료',
  EXTERNAL_CONNECTED: '불확실성이 남을 때 동의를 받아 확인하는 외부 연결 정보',
}
const formatDate = (value: string | null) => value
  ? new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
  : '해당 없음'

function SourceCard({ source, busy, error, onRetry }: {
  source: DataSourceState
  busy: boolean
  error?: ApiError
  onRetry?: () => void
}) {
  return (
    <article className={`source-card source-card--${source.retrievalStatus.toLowerCase()}`}>
      <div className="source-card__top">
        <span className="source-card__icon" aria-hidden="true">{statusIcon[source.retrievalStatus]}</span>
        <div>
          <span className="source-card__scope">기존 평가 확인</span>
          <h3>{source.displayName}</h3>
        </div>
      </div>
      <dl className="source-card__summary">
        <div><dt>확인 대상</dt><dd>{sourcePurpose[source.sourceType]}</dd></div>
        <div><dt>데이터 기준시점</dt><dd>{source.observedAt ? formatDate(source.observedAt) : '조회 후 표시'}</dd></div>
      </dl>
      <div className="status-row">
        <span className="status-row__retrieval">연결 상태 · {retrievalLabel[source.retrievalStatus]}</span>
        <span className={`status-row__verification status-row__verification--${source.verificationStatus.toLowerCase()}`}>정보 확인 · {verificationLabel[source.verificationStatus]}</span>
      </div>
      <CustomerTechnicalDetails>
        <dl>
          <div><dt>출처 유형</dt><dd>{source.sourceType}</dd></div>
          <div><dt>데이터 기준시점</dt><dd>{formatDate(source.observedAt)}</dd></div>
          <div><dt>시스템 조회시점</dt><dd>{formatDate(source.retrievedAt)}</dd></div>
          <div><dt>데이터 버전</dt><dd>{source.dataVersion ?? '해당 없음'}</dd></div>
        </dl>
        {source.reasonCode && <p className="source-card__reason">상태 코드: <span>{source.reasonCode}</span></p>}
      </CustomerTechnicalDetails>
      {error && <p className="source-card__error" role="alert">{error.message}{error.requestId ? <small>Request ID: {error.requestId}</small> : null}</p>}
      {source.retrievalStatus === 'FAILED' && onRetry && (
        <button className="retry-button" type="button" onClick={onRetry} disabled={busy}>
          {busy ? '이 항목 재시도 중…' : `${source.displayName} 다시 조회`}
        </button>
      )}
    </article>
  )
}

function DataConnectionPage() {
  const navigate = useNavigate()
  const { session, loading: sessionLoading } = useCustomerSession()
  const sessionId = session?.sessionId
  const [result, setResult] = useState<DataSourceListResponse | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [itemErrors, setItemErrors] = useState<Partial<Record<ConsentSourceType, ApiError>>>({})
  const [isLoading, setIsLoading] = useState(true)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [retrying, setRetrying] = useState<ConsentSourceType | null>(null)
  const requestSequence = useRef(0)
  const controllerRef = useRef<AbortController | null>(null)

  useEffect(() => {
    if (!sessionLoading && !session) navigate('/start', { replace: true })
  }, [navigate, session, sessionLoading])

  const load = useCallback(async (refresh = false): Promise<DataSourceListResponse | null> => {
    if (!sessionId) return null
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller
    const sequence = ++requestSequence.current
    setIsLoading(true)
    setIsRefreshing(refresh)
    setError(null)
    setItemErrors({})
    try {
      const next = await (refresh
        ? dataConnectionProvider.refresh(sessionId, controller.signal)
        : dataConnectionProvider.list(sessionId, controller.signal))
      if (sequence === requestSequence.current) setResult(next)
      return next
    } catch (caught) {
      if (!controller.signal.aborted && sequence === requestSequence.current) setError(normalizeDataConnectionError(caught))
      return null
    } finally {
      if (sequence === requestSequence.current) {
        setIsLoading(false)
        setIsRefreshing(false)
      }
    }
  }, [sessionId])

  const refreshBaselineSources = () => void load(true)

  useEffect(() => {
    if (sessionId) queueMicrotask(() => void load())
    return () => {
      requestSequence.current += 1
      controllerRef.current?.abort()
    }
  }, [load, sessionId])

  const retrySource = async (sourceType: ConsentSourceType) => {
    if (!session || !dataConnectionProvider.retrySource || retrying) return
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller
    const sequence = ++requestSequence.current
    setRetrying(sourceType)
    setItemErrors((current) => ({ ...current, [sourceType]: undefined }))
    try {
      const source = await dataConnectionProvider.retrySource(session.sessionId, sourceType, controller.signal)
      if (sequence === requestSequence.current) {
        setResult((current) => current
          ? { ...current, dataSources: current.dataSources.map((item) => item.sourceType === sourceType ? source : item) }
          : current)
      }
    } catch (caught) {
      if (!controller.signal.aborted && sequence === requestSequence.current) {
        setItemErrors((current) => ({ ...current, [sourceType]: normalizeDataConnectionError(caught) }))
      }
    } finally {
      if (sequence === requestSequence.current) setRetrying(null)
    }
  }

  if (sessionLoading || !session) return null

  const baselineSources = result?.dataSources.filter((source) => baselineSourceTypes.includes(source.sourceType)) ?? []
  const retrievedCount = baselineSources.filter((source) => source.retrievalStatus === 'RETRIEVED').length
  const verifiedCount = baselineSources.filter((source) => source.verificationStatus === 'VERIFIED').length
  const baselineReady = baselineSources.length === baselineSourceTypes.length
    && baselineSources.every((source) => source.retrievalStatus === 'RETRIEVED' && source.verificationStatus === 'VERIFIED')
  const refreshAttempted = baselineSources.some((source) => !['NOT_REQUESTED', 'CONSENT_REQUIRED'].includes(source.retrievalStatus))
  const statusMessage = isLoading
    ? isRefreshing
      ? '은행 내부 데이터와 신용정보를 조회하고 기준시점과 상태를 검증하고 있습니다.'
      : '기존 평가 확인에 필요한 데이터 출처 상태를 확인하고 있습니다.'
    : retrying
      ? `${result?.dataSources.find((item) => item.sourceType === retrying)?.displayName} 항목을 다시 확인하고 있습니다.`
      : error
        ? '데이터 출처 상태를 확인하지 못했습니다.'
        : baselineReady
          ? '기존 평가 확인에 필요한 두 출처의 조회와 검증이 완료됐습니다.'
          : refreshAttempted
            ? '조회 결과에서 확인이 필요한 항목이 있습니다.'
            : '동의한 범위에서 기존 평가 데이터를 불러올 준비가 됐습니다.'

  return (
    <div className="workspace-shell customer-flow">
      <Header />
      <main id="main-content" tabIndex={-1} className="connection-page">
        <div className="container connection-page__inner">
          <CustomerFlowSteps current="data-connection" className="flow-steps" />
          <header className="connection-heading">
            <div>
              <h1 className="page-title-lines"><span>기존 평가 데이터의</span><span>연결 상태를 확인합니다</span></h1>
              <p>동의한 범위에서 평가에 필요한 정보가 준비됐는지 확인합니다. 정보가 없거나 추가 동의가 필요해도 신용상 불리한 결과를 뜻하지 않습니다.</p>
            </div>
            <aside>
              <span>현재 사업자 유형</span>
              <strong>{session.demoProfile.displayName}</strong>
              <small>평가 주체와 연결 데이터가 이 유형에 맞게 적용됩니다.</small>
            </aside>
          </header>

          <div className="connection-status" aria-live="polite" role="status">{statusMessage}</div>
          {error && (
            <section className="connection-error" role="alert">
              <div><strong>{error.message}</strong><small>오류 코드: {error.code}{error.requestId ? ` · Request ID: ${error.requestId}` : ''}</small></div>
              {error.retryable && <button type="button" onClick={() => void load()}>다시 확인</button>}
            </section>
          )}
          {isLoading && !result && <div className="source-skeletons" aria-hidden="true"><span /><span /><span /><span /></div>}
          {!isLoading && !error && result?.dataSources.length === 0 && (
            <section className="empty-sources">
              <h2>표시할 데이터 출처가 없습니다</h2>
              <p>현재 세션에서 확인 가능한 데이터 출처가 반환되지 않았습니다.</p>
            </section>
          )}
          {result && baselineSources.length > 0 && (
            <section className="source-section" aria-labelledby="source-title">
              <div className="source-section__heading">
                <div><span>01</span><h2 id="source-title">기존 평가 필수 데이터</h2></div>
                <p>CB와 은행 내부 정보, 해당 은행이 사용하는 경우 SCB가 포함된 기존 평가를 확인합니다.</p>
              </div>
              <div className="source-grid">
                {baselineSources.map((source) => (
                  <SourceCard
                    key={source.sourceType}
                    source={source}
                    busy={retrying === source.sourceType}
                    error={itemErrors[source.sourceType]}
                    onRetry={dataConnectionProvider.retrySource ? () => void retrySource(source.sourceType) : undefined}
                  />
                ))}
              </div>
              <section className={`connection-pipeline ${baselineReady ? 'connection-pipeline--ready' : ''}`} aria-labelledby="pipeline-title">
                <div className="connection-pipeline__heading">
                  <div><span>02</span><h2 id="pipeline-title">기존 평가 확인 준비</h2></div>
                  <strong>{baselineReady ? '준비 완료' : isRefreshing ? '조회·검증 중' : '준비 전'}</strong>
                </div>
                <ol>
                  <li className="is-complete"><span>1</span><div><strong>동의 범위 확인</strong><p>고객이 확인한 필수 동의 범위를 적용합니다.</p></div><b>완료</b></li>
                  <li className={retrievedCount === baselineSourceTypes.length ? 'is-complete' : isRefreshing ? 'is-active' : ''}><span>2</span><div><strong>필수 출처 조회</strong><p>은행 내부 데이터와 신용정보를 서버에서 조회합니다.</p></div><b>{isRefreshing ? '진행 중' : `${retrievedCount}/2 완료`}</b></li>
                  <li className={verifiedCount === baselineSourceTypes.length ? 'is-complete' : retrievedCount > 0 || isRefreshing ? 'is-active' : ''}><span>3</span><div><strong>기준시점·상태 검증</strong><p>조회된 정보의 기준시점과 검증 상태를 확인합니다.</p></div><b>{verifiedCount}/2 완료</b></li>
                  <li className={baselineReady ? 'is-complete' : ''}><span>4</span><div><strong>기존 평가 확인 준비</strong><p>검증된 데이터로 은행이 이미 보유한 평가 결과와 기준시점을 확인합니다.</p></div><b>{baselineReady ? '준비 완료' : '대기'}</b></li>
                </ol>
                <p className="connection-pipeline__notice">고객 제출 자료와 외부 기관 연결은 기존 평가의 불확실성이 남아 추가 확인이 필요할 때만 요청합니다.</p>
              </section>
            </section>
          )}

          <section className="connection-actions" aria-label="데이터 연결 다음 작업">
            <div>
              <strong>{baselineReady ? '기존 평가 확인 준비가 됐습니다' : '기존 평가 확인에 필요한 데이터를 먼저 불러오세요'}</strong>
              <p>{baselineReady ? '다음 단계에서 은행이 보유한 기존 평가 결과와 정책 경계를 확인합니다.' : '조회가 끝나면 출처별 기준시점과 검증 결과를 이 화면에서 확인할 수 있습니다.'}</p>
            </div>
            <div className="connection-actions__buttons">
              <Link className="connection-actions__consent" to="/consent">동의 내용 수정</Link>
              {result && (baselineReady
                ? <button className="button button--primary" type="button" onClick={() => navigate('/assessment')} disabled={isLoading || Boolean(retrying)}>기존 평가 결과 확인</button>
                : <button className="button button--primary" type="button" onClick={refreshBaselineSources} disabled={isLoading || Boolean(retrying)}>{isRefreshing ? '데이터 조회·검증 중…' : refreshAttempted ? '데이터 다시 불러오기' : '기존 평가 데이터 불러오기'}</button>)}
            </div>
          </section>
        </div>
      </main>
    </div>
  )
}

export default DataConnectionPage
