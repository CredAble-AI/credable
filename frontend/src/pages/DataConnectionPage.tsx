import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { normalizeDataConnectionError } from '../api/dataConnectionClient'
import Header from '../components/Header'
import { isMockMode } from '../config/providerMode'
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
          <span className="source-card__scope">{source.sourceType} · Demo 데이터</span>
          <h3>{source.displayName}</h3>
        </div>
      </div>
      <div className="status-row">
        <span className="status-row__retrieval">조회 · {retrievalLabel[source.retrievalStatus]}</span>
        <span className={`status-row__verification status-row__verification--${source.verificationStatus.toLowerCase()}`}>검증 · {verificationLabel[source.verificationStatus]}</span>
        {isMockMode && <span className="status-row__environment">Mock 데이터</span>}
      </div>
      <details className="source-card__details">
        <summary>상세 추적 정보</summary>
        <dl>
          <div><dt>출처 유형</dt><dd>{source.sourceType}</dd></div>
          <div><dt>데이터 기준시점</dt><dd>{formatDate(source.observedAt)}</dd></div>
          <div><dt>시스템 조회시점</dt><dd>{formatDate(source.retrievedAt)}</dd></div>
          <div><dt>데이터 버전</dt><dd>{source.dataVersion ?? '해당 없음'}</dd></div>
        </dl>
        {source.reasonCode && <p className="source-card__reason">상태 코드: <span>{source.reasonCode}</span></p>}
      </details>
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
  const [result, setResult] = useState<DataSourceListResponse | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [itemErrors, setItemErrors] = useState<Partial<Record<ConsentSourceType, ApiError>>>({})
  const [isLoading, setIsLoading] = useState(true)
  const [retrying, setRetrying] = useState<ConsentSourceType | null>(null)
  const requestSequence = useRef(0)
  const controllerRef = useRef<AbortController | null>(null)

  useEffect(() => {
    if (!sessionLoading && !session) navigate('/start', { replace: true })
  }, [navigate, session, sessionLoading])

  const load = useCallback(async (refresh = false) => {
    if (!session) return
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller
    const sequence = ++requestSequence.current
    setIsLoading(true)
    setError(null)
    setItemErrors({})
    try {
      const next = await (refresh
        ? dataConnectionProvider.refresh(session.sessionId, controller.signal)
        : dataConnectionProvider.list(session.sessionId, controller.signal))
      if (sequence === requestSequence.current) setResult(next)
    } catch (caught) {
      if (!controller.signal.aborted && sequence === requestSequence.current) setError(normalizeDataConnectionError(caught))
    } finally {
      if (sequence === requestSequence.current) setIsLoading(false)
    }
  }, [session])

  useEffect(() => {
    if (session) queueMicrotask(() => void load())
    return () => {
      requestSequence.current += 1
      controllerRef.current?.abort()
    }
  }, [load, session])

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

  const statusMessage = isLoading
    ? '데이터 출처 상태를 확인하고 있습니다.'
    : retrying
      ? `${result?.dataSources.find((item) => item.sourceType === retrying)?.displayName} 항목을 다시 확인하고 있습니다.`
      : error
        ? '데이터 출처 상태를 확인하지 못했습니다.'
        : '서버가 반환한 현재 데이터 출처 상태입니다.'

  return (
    <div className="workspace-shell customer-flow">
      <Header />
      <main id="main-content" tabIndex={-1} className="connection-page">
        <div className="container connection-page__inner">
          <nav className="flow-steps" aria-label="진행 단계">
            <span>시작</span><span>동의</span><strong aria-current="step">데이터 연결</strong><span>기준평가</span><span>상품 비교</span>
          </nav>
          <header className="connection-heading">
            <div>
              {isMockMode && <span className="connection-badge">Mock mode · Demo Only</span>}
              <p className="flow-kicker">DATA CONNECTION</p>
              <h1>기준평가에 사용할 데이터 출처를 확인합니다</h1>
              <p>서버가 확인한 조회·검증 상태를 그대로 보여줍니다. 동의가 필요하거나 데이터가 없다는 상태를 연결 실패 또는 신용상 불리한 결과로 해석하지 않습니다.</p>
            </div>
            <aside>
              <span>현재 사업자 유형</span>
              <strong>{session.demoProfile.displayName}</strong>
              <small>합성 Demo 사례이며 실제 고객 정보를 사용하지 않습니다.</small>
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
          {result && result.dataSources.length > 0 && (
            <section className="source-section" aria-labelledby="source-title">
              <div className="source-section__heading">
                <div><span>01</span><h2 id="source-title">데이터 출처별 상태</h2></div>
                <p>백엔드 응답 순서와 상태를 유지합니다.</p>
              </div>
              <div className="source-grid">
                {result.dataSources.map((source) => (
                  <SourceCard
                    key={source.sourceType}
                    source={source}
                    busy={retrying === source.sourceType}
                    error={itemErrors[source.sourceType]}
                    onRetry={dataConnectionProvider.retrySource ? () => void retrySource(source.sourceType) : undefined}
                  />
                ))}
              </div>
            </section>
          )}

          <section className="connection-actions" aria-label="데이터 연결 다음 작업">
            <div>
              <strong>{result ? '데이터 출처 상태를 확인했습니다' : '데이터 출처 상태를 확인해주세요'}</strong>
              <p>평가 실행 가능 여부와 결과 상태는 다음 단계에서 백엔드가 확정합니다.</p>
            </div>
            <div className="connection-actions__buttons">
              <Link className="button button--secondary" to="/consent">동의 범위 확인</Link>
              <button className="button button--secondary" type="button" onClick={() => void load(true)} disabled={isLoading || Boolean(retrying)}>전체 출처 새로고침</button>
              {result && !isLoading && !retrying && <Link className="button button--primary" to="/assessment">기준평가 실행</Link>}
            </div>
          </section>
        </div>
      </main>
    </div>
  )
}

export default DataConnectionPage
