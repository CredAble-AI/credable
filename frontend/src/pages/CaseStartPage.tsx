import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Header from '../components/Header'
import { normalizeApiError } from '../api/caseClient'
import { demoCases } from '../data/demoCases'
import { mockDemoCaseProvider } from '../mocks/demoCaseProvider'
import type { ApiError, DemoCaseType } from '../types/case'
import './CaseStartPage.css'

const provider = mockDemoCaseProvider

function CaseStartPage() {
  const navigate = useNavigate()
  const [selectedType, setSelectedType] = useState<DemoCaseType | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const submittingRef = useRef(false)

  const createCase = async () => {
    if (!selectedType || submittingRef.current) return
    submittingRef.current = true
    setIsSubmitting(true)
    setError(null)
    try {
      const response = await provider.create({ demoCaseType: selectedType })
      sessionStorage.setItem('credable.caseId', response.caseId)
      sessionStorage.removeItem('credable.evidenceSubmitted')
      navigate('/eligibility')
    } catch (caughtError) {
      setError(normalizeApiError(caughtError))
    } finally {
      submittingRef.current = false
      setIsSubmitting(false)
    }
  }

  return (
    <div className="workspace-shell">
      <Header />
      <main className="case-page">
        <div className="case-page__glow" aria-hidden="true" />
        <div className="container case-page__inner">
          <div className="case-heading">
            <div className="demo-badge"><span aria-hidden="true" />Mock mode · Demo Only</div>
            <p className="eyebrow">START SECOND-LOOK</p>
            <h1>검토할 Case를 선택해주세요</h1>
            <p>거절·보류 사유가 서로 다른 네 가지 시나리오로 Second-Look 흐름을 확인할 수 있습니다.</p>
          </div>
          <aside className="scope-panel" aria-label="초기 적용 범위">
            <strong>Initial Scope</strong>
            <p>음식업 개인사업자 <span>·</span> 업력 6개월 이상 <span>·</span> 소액 운전자금 <span>·</span> 적격 Reason Code</p>
          </aside>
          <fieldset className="case-grid" disabled={isSubmitting}>
            <legend className="sr-only">Demo Case 선택</legend>
            {demoCases.map((item) => {
              const selected = selectedType === item.type
              return (
                <label className={`case-card${selected ? ' case-card--selected' : ''}`} key={item.type}>
                  <input type="radio" name="demo-case" value={item.type} checked={selected} onChange={() => setSelectedType(item.type)} />
                  <span className="case-card__check" aria-hidden="true">{selected ? '✓' : ''}</span>
                  <span className={`decision decision--${item.currentDecision.toLowerCase()}`}>{item.currentDecision === 'HELD' ? '보류' : '거절'}</span>
                  <h2>{item.name}</h2>
                  <p className="case-card__description">{item.description}</p>
                  <dl><div><dt>업력</dt><dd>{item.tenureMonths}개월</dd></div><div><dt>상품</dt><dd>{item.productType}</dd></div><div><dt>Reason</dt><dd>{item.reasons.join(' · ')}</dd></div></dl>
                </label>
              )
            })}
          </fieldset>
          {error && <div className="error-panel" role="alert"><div><strong>{error.message}</strong><small>오류 코드: {error.code}{error.requestId ? ` · 요청 ID: ${error.requestId}` : ''} · 재시도 가능: {error.retryable ? '예' : '아니오'}</small></div><button type="button" onClick={createCase} disabled={isSubmitting || !error.retryable}>재시도</button></div>}
          <div className="case-submit"><button className="button button--primary" type="button" disabled={!selectedType || isSubmitting} onClick={createCase}>{isSubmitting ? 'Case 생성 중…' : '선택한 Case 검토하기'}</button><p aria-live="polite">{isSubmitting ? '선택한 Demo Case를 생성하고 있습니다.' : '선택한 Case의 다음 검토 단계로 이동합니다.'}</p></div>
        </div>
      </main>
    </div>
  )
}
export default CaseStartPage
