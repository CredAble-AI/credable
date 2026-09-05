import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { normalizeConsentError } from '../api/consentClient'
import Header from '../components/Header'
import { consentProvider } from '../hooks/useConsentState'
import { useCustomerSession } from '../hooks/useCustomerSession'
import type { ApiError } from '../types/api'
import type { ConsentSourceType, ConsentState } from '../types/consent'
import './ConsentPage.css'

const requirementLabel = (required: boolean | null) => {
  if (required === true) return '필수 · Demo 데이터'
  if (required === false) return '선택 · Demo 데이터'
  return '필수 여부 미확정 · Demo 데이터'
}

const statusLabel = (status: ConsentState['status']) => {
  if (status === 'GRANTED') return '동의함'
  if (status === 'WITHDRAWN') return '동의 철회됨'
  return '미동의'
}

function ConsentPage() {
  const navigate = useNavigate()
  const { session, loading: sessionLoading } = useCustomerSession()
  const [consents, setConsents] = useState<ConsentState[]>([])
  const [scopeVersion, setScopeVersion] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [updatingSource, setUpdatingSource] = useState<ConsentSourceType | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [message, setMessage] = useState('')
  const loadControllerRef = useRef<AbortController | null>(null)
  const actionControllerRef = useRef<AbortController | null>(null)
  const sequenceRef = useRef(0)

  const loadConsents = useCallback(async (sessionId: string) => {
    loadControllerRef.current?.abort()
    const controller = new AbortController()
    loadControllerRef.current = controller
    const sequence = ++sequenceRef.current
    setLoading(true)
    setError(null)
    setMessage('')
    try {
      const response = await consentProvider.list(sessionId, controller.signal)
      if (sequence !== sequenceRef.current) return
      setConsents(response.consents)
      setScopeVersion(response.scopeVersion)
    } catch (caught) {
      if (!controller.signal.aborted && sequence === sequenceRef.current) setError(normalizeConsentError(caught))
    } finally {
      if (sequence === sequenceRef.current) setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!sessionLoading && !session) navigate('/start', { replace: true })
  }, [navigate, session, sessionLoading])

  useEffect(() => {
    if (!session) return
    queueMicrotask(() => void loadConsents(session.sessionId))
    return () => {
      sequenceRef.current += 1
      loadControllerRef.current?.abort()
      actionControllerRef.current?.abort()
    }
  }, [loadConsents, session])

  if (sessionLoading || !session) return null

  const requiredConsents = consents.filter((consent) => consent.required === true)
  const requiredComplete = requiredConsents.every((consent) => consent.status === 'GRANTED')
  const canContinue = !loading && consents.length > 0 && requiredComplete && !updatingSource

  const toggleConsent = async (consent: ConsentState) => {
    if (updatingSource) return
    actionControllerRef.current?.abort()
    const controller = new AbortController()
    actionControllerRef.current = controller
    setUpdatingSource(consent.sourceType)
    setError(null)
    setMessage('')
    try {
      const updated = consent.status === 'GRANTED'
        ? await consentProvider.withdraw(session.sessionId, consent.sourceType, controller.signal)
        : await consentProvider.grant(session.sessionId, consent.sourceType, controller.signal)
      if (controller.signal.aborted) return
      setConsents((current) => current.map((item) => item.sourceType === updated.sourceType ? updated : item))
      setMessage(`${updated.displayName} 동의를 ${updated.status === 'GRANTED' ? '반영했습니다.' : '철회했습니다.'}`)
    } catch (caught) {
      if (!controller.signal.aborted) setError(normalizeConsentError(caught))
    } finally {
      if (!controller.signal.aborted) setUpdatingSource(null)
    }
  }

  const progressMessage = error?.message
    || message
    || (loading
      ? '데이터 이용 동의 범위를 불러오는 중입니다.'
      : requiredComplete
        ? requiredConsents.length === 0
          ? '서버에서 필수로 지정한 항목이 없습니다. 현재 동의한 범위로 계속할 수 있습니다.'
          : '서버에서 필수로 지정한 항목이 모두 충족되었습니다. 현재 동의한 범위로 계속할 수 있습니다.'
      : '계속하려면 서버에서 필수로 지정한 항목에 동의해주세요.')

  return (
    <div className="workspace-shell customer-flow">
      <Header />
      <main id="main-content" tabIndex={-1} className="consent-page">
        <div className="container consent-page__inner">
          <header className="consent-heading">
            <div><p className="flow-kicker">DATA CONSENT</p><h1>연결할 데이터의 이용 범위를 확인해주세요</h1><p>각 항목의 설명과 필수 여부는 서버가 제공한 동의 범위를 그대로 표시합니다. 동의는 실제 데이터 연결 성공을 보장하지 않습니다.</p></div>
            <div className="session-summary"><span>Demo Only</span><strong>{session.demoProfile.displayName}</strong><small>{scopeVersion ? `동의 범위 ${scopeVersion}` : '동의 범위 확인 중'}</small></div>
          </header>

          {loading && <p className="consent-state" role="status" aria-live="polite">데이터 이용 동의 상태를 불러오고 있습니다.</p>}
          {!loading && error && consents.length === 0 && (
            <div className="consent-state consent-state--error" role="alert">
              <p>{error.message}</p>
              {error.requestId && <small>요청 ID {error.requestId}</small>}
              <button className="button button--secondary" type="button" onClick={() => void loadConsents(session.sessionId)}>다시 시도</button>
            </div>
          )}
          {!loading && !error && consents.length === 0 && <p className="consent-state" role="status">현재 확인할 수 있는 데이터 이용 동의 항목이 없습니다.</p>}

          {!loading && consents.length > 0 && (
            <fieldset className="consent-group">
              <legend><span>데이터 이용 동의</span><strong>서버에 등록된 범위와 현재 상태입니다</strong></legend>
              {consents.map((consent) => {
                const checked = consent.status === 'GRANTED'
                const isUpdating = updatingSource === consent.sourceType
                return (
                  <label className="consent-item" key={consent.sourceType}>
                    <input type="checkbox" checked={checked} disabled={Boolean(updatingSource)} onChange={() => void toggleConsent(consent)} />
                    <span className="consent-item__box" aria-hidden="true">✓</span>
                    <span className="consent-item__content">
                      <strong>{consent.displayName}</strong>
                      <small className="consent-item__description">{consent.description}</small>
                      <small className="consent-item__status"><b>현재 상태</b>{isUpdating ? '처리 중' : statusLabel(consent.status)}</small>
                      <em className={consent.required === true ? 'consent-item__requirement--required' : ''}>{requirementLabel(consent.required)}</em>
                    </span>
                  </label>
                )
              })}
            </fieldset>
          )}

          <div className="consent-actions">
            {(!error || consents.length > 0) && <p className={error ? 'consent-actions__message--error' : ''} role={error ? 'alert' : 'status'} aria-live="polite">{progressMessage}</p>}
            <div><Link className="button button--secondary" to="/start">이전으로</Link><button className="button button--primary" type="button" disabled={!canContinue} onClick={() => navigate('/data-connection')}>데이터 연결로 이동</button></div>
          </div>
        </div>
      </main>
    </div>
  )
}

export default ConsentPage
