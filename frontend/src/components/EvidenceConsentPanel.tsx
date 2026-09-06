import { useCallback, useEffect, useRef, useState } from 'react'
import { normalizeEvidenceConsentError } from '../api/evidenceConsentClient'
import { evidenceConsentProvider } from '../hooks/useEvidenceConsentState'
import type { ApiError } from '../types/api'
import type { EvidenceConsentResponse, EvidenceConsentState } from '../types/evidenceConsent'
import CustomerTechnicalDetails from './CustomerTechnicalDetails'

interface EvidenceConsentPanelProps {
  sessionId: string
  selectionId: string
  evidenceType: string
  onConsentChanged: () => void
}

const statusLabel = { PENDING: '미동의', GRANTED: '동의함', WITHDRAWN: '동의 철회됨' } as const
const dataCategoryLabels: Record<string, string> = {
  BUSINESS_IDENTITY: '사업자 식별 정보',
  MONTHLY_SALES: '월별 매출',
  MONTHLY_DEPOSITS: '월별 입금',
  PERIOD_TOTALS: '대상 기간 합계',
  SETTLEMENT_PROVIDER_IDENTITY: '정산기관 식별 정보',
  MONTHLY_SETTLEMENTS: '월별 정산액',
  SETTLEMENT_DEPOSITS: '정산대금 입금 내역',
}

function EvidenceConsentPanel({ sessionId, selectionId, evidenceType, onConsentChanged }: EvidenceConsentPanelProps) {
  const [consent, setConsent] = useState<EvidenceConsentState | null>(null)
  const [loading, setLoading] = useState(true)
  const [updating, setUpdating] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const [message, setMessage] = useState('')
  const controllerRef = useRef<AbortController | null>(null)
  const sequenceRef = useRef(0)

  const acceptResponse = useCallback((response: EvidenceConsentResponse) => {
    if (response.sessionId !== sessionId || response.selectionId !== selectionId || response.consent.selectionId !== selectionId || response.consent.evidenceType !== evidenceType) {
      throw { code: 'EVIDENCE_CONSENT_CONTEXT_MISMATCH', message: '현재 선택한 증빙과 일치하는 동의 상태를 확인할 수 없습니다.', retryable: true } satisfies ApiError
    }
    return response.consent
  }, [evidenceType, selectionId, sessionId])

  const load = useCallback(async () => {
    controllerRef.current?.abort()
    const controller = new AbortController(); controllerRef.current = controller
    const sequence = ++sequenceRef.current
    setLoading(true); setConsent(null); setError(null); setMessage('')
    try {
      const response = await evidenceConsentProvider.get(sessionId, selectionId, controller.signal)
      if (sequence === sequenceRef.current) setConsent(acceptResponse(response))
    } catch (caught) {
      if (!controller.signal.aborted && sequence === sequenceRef.current) setError(normalizeEvidenceConsentError(caught))
    } finally {
      if (sequence === sequenceRef.current) setLoading(false)
    }
  }, [acceptResponse, selectionId, sessionId])

  useEffect(() => {
    queueMicrotask(() => void load())
    return () => { sequenceRef.current += 1; controllerRef.current?.abort() }
  }, [load])

  const update = async () => {
    if (!consent || updating) return
    controllerRef.current?.abort()
    const controller = new AbortController(); controllerRef.current = controller
    const sequence = ++sequenceRef.current
    setUpdating(true); setError(null); setMessage('')
    try {
      const response = consent.status === 'GRANTED'
        ? await evidenceConsentProvider.withdraw(sessionId, selectionId, controller.signal)
        : await evidenceConsentProvider.grant(sessionId, selectionId, controller.signal)
      const updated = acceptResponse(response)
      if (sequence === sequenceRef.current) {
        setConsent(updated)
        setMessage(updated.status === 'GRANTED' ? '이 증빙의 이용 동의를 반영했습니다.' : '이 증빙의 이용 동의를 철회했습니다.')
        onConsentChanged()
      }
    } catch (caught) {
      if (!controller.signal.aborted && sequence === sequenceRef.current) setError(normalizeEvidenceConsentError(caught))
    } finally {
      if (sequence === sequenceRef.current) setUpdating(false)
    }
  }

  if (loading && !consent) return <div className="evidence-consent evidence-consent--loading" role="status">증빙 이용 동의 범위를 확인하고 있습니다.</div>
  if (!consent) return <div className="evidence-consent evidence-consent--error" role="alert"><p>{error?.message ?? '증빙 이용 동의 범위를 확인할 수 없습니다.'}</p>{error?.requestId && <small>요청 ID {error.requestId}</small>}<button type="button" onClick={() => void load()}>다시 확인</button></div>

  return <section className="evidence-consent" aria-labelledby="evidence-consent-title">
    <div className="evidence-consent__heading"><div><h3 id="evidence-consent-title">이 자료에서 확인할 정보</h3></div><strong className={`evidence-consent__status evidence-consent__status--${consent.status.toLowerCase()}`}>{statusLabel[consent.status]}</strong></div>
    <p>{consent.purposeDescription}</p>
    <dl><div><dt>확인할 정보</dt><dd><ul className="evidence-consent__categories">{consent.dataCategories.map((category) => <li key={category}>{dataCategoryLabels[category] ?? category}</li>)}</ul></dd></div><div><dt>확인 기간</dt><dd>{consent.periodStart} ~ {consent.periodEnd}</dd></div></dl>
    <CustomerTechnicalDetails><dl><div><dt>동의 범위 버전</dt><dd><code>{consent.scopeVersion}</code></dd></div><div><dt>원본 데이터 항목</dt><dd><code>{consent.dataCategories.join(', ')}</code></dd></div></dl></CustomerTechnicalDetails>
    <div className="evidence-consent__action"><p className={error ? 'evidence-consent__message--error' : ''} role={error ? 'alert' : 'status'} aria-live="polite">{error?.message || message || '현재 요청한 자료에 포함된 정보만 보완평가에 사용합니다.'}</p><button className={consent.status === 'GRANTED' ? 'button button--secondary' : 'button button--primary'} type="button" disabled={updating} onClick={() => void update()}>{updating ? '처리 중…' : consent.status === 'GRANTED' ? '이 동의 철회' : '이 범위에 동의'}</button></div>
  </section>
}

export default EvidenceConsentPanel
