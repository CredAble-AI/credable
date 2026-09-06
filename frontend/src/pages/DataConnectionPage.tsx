import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { normalizeDataConnectionError } from '../api/dataConnectionClient'
import Header from '../components/Header'
import CustomerTechnicalDetails from '../components/CustomerTechnicalDetails'
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
          <span className="source-card__scope">평가에 연결된 정보</span>
          <h3>{source.displayName}</h3>
        </div>
      </div>
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
      if (sequence === requestSequence.current) setIsLoading(false)
    }
  }, [sessionId])

  const continueToAssessment = async () => {
    const refreshed = await load(true)
    if (refreshed) navigate('/assessment')
  }

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

  const statusMessage = isLoading
    ? '데이터 출처 상태를 확인하고 있습니다.'
    : retrying
      ? `${result?.dataSources.find((item) => item.sourceType === retrying)?.displayName} 항목을 다시 확인하고 있습니다.`
      : error
        ? '데이터 출처 상태를 확인하지 못했습니다.'
        : '연결된 정보의 현재 상태를 확인했습니다.'

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
              {isMockMode && <span className="connection-badge">시연용 합성 데이터</span>}
              <p className="flow-kicker">DATA CONNECTION</p>
              <h1>기준평가에 사용할 데이터 출처를 확인합니다</h1>
              <p>동의한 범위에서 평가에 필요한 정보가 준비됐는지 확인합니다. 정보가 없거나 추가 동의가 필요해도 신용상 불리한 결과를 뜻하지 않습니다.</p>
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
              <p>평가에 사용되는 정보가 준비됐는지 한눈에 확인할 수 있습니다.</p>
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
              <strong>{result ? '다음은 기준평가입니다' : '데이터 출처 상태를 확인해주세요'}</strong>
              <p>최신 연결 상태를 한 번 확인한 뒤 기준평가 화면으로 이동합니다.</p>
            </div>
            <div className="connection-actions__buttons">
              <Link className="connection-actions__consent" to="/consent">동의 내용 수정</Link>
              {result && <button className="button button--primary" type="button" onClick={() => void continueToAssessment()} disabled={isLoading || Boolean(retrying)}>{isLoading ? '데이터 확인 중…' : '데이터 확인 후 기준평가 시작'}</button>}
            </div>
          </section>
        </div>
      </main>
    </div>
  )
}

export default DataConnectionPage
