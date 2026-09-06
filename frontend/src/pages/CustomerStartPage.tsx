import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { normalizeSessionError } from '../api/sessionClient'
import Header from '../components/Header'
import { sessionProvider } from '../hooks/useCustomerSession'
import type { ApiError } from '../types/api'
import type { BusinessBorrowerType, DemoProfile } from '../types/customerSession'
import './CustomerStartPage.css'

function CustomerStartPage() {
  const navigate = useNavigate()
  const [profiles, setProfiles] = useState<DemoProfile[]>([])
  const [profilesLoading, setProfilesLoading] = useState(true)
  const [profilesError, setProfilesError] = useState<ApiError | null>(null)
  const [selected, setSelected] = useState<BusinessBorrowerType | null>(null)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const sequenceRef = useRef(0)

  const controllerRef = useRef<AbortController | null>(null)
  const loadProfiles = useCallback(async () => {
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller
    const sequence = ++sequenceRef.current
    setProfilesLoading(true)
    setProfilesError(null)
    try {
      const result = await sessionProvider.listDemoProfiles(controller.signal)
      if (sequence === sequenceRef.current) setProfiles(result)
    } catch (caught) {
      if (!controller.signal.aborted && sequence === sequenceRef.current) setProfilesError(normalizeSessionError(caught))
    } finally {
      if (sequence === sequenceRef.current) setProfilesLoading(false)
    }
  }, [])
  useEffect(() => {
    queueMicrotask(() => void loadProfiles())
    return () => { sequenceRef.current += 1; controllerRef.current?.abort() }
  }, [loadProfiles])

  const continueToConsent = async () => {
    if (!selected) {
      setError('개인사업자 또는 법인사업자를 선택해주세요.')
      return
    }
    setSubmitting(true)
    setError('')
    try {
      await sessionProvider.create(selected, new AbortController().signal)
      navigate('/consent')
    } catch (caught) {
      setError(normalizeSessionError(caught).message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="workspace-shell customer-flow">
      <Header />
      <main id="main-content" tabIndex={-1} className="customer-page">
        <div className="container customer-page__inner">
          <div className="flow-heading">
            <p className="flow-kicker">평가 시작</p>
            <span className="demo-badge"><i aria-hidden="true" />시연용 합성 데이터</span>
            <h1>대출 계약의 주체를 선택해주세요</h1>
            <p>CredAble은 사업자금 대출을 탐색하는 등록 사업자를 위한 서비스입니다. 선택한 사업자 유형에 맞는 합성 사례로 평가 흐름을 확인합니다.</p>
          </div>

          <aside className="demo-journey-note" aria-label="시연 자료 이용 방법">
            <strong>시연 중 직접 확인할 수 있습니다</strong>
            <p>최소 증빙이 필요한 단계에서 정상·기준시점 오류·변조 의심 PDF를 화면에서 내려받고, 같은 화면에서 다시 업로드해 검증 결과를 확인합니다.</p>
          </aside>

          {profilesLoading && <p role="status" aria-live="polite">사업자 유형을 불러오고 있습니다.</p>}
          {profilesError && (
            <div className="flow-actions">
              <p className="flow-error" role="alert">{profilesError.message}</p>
              <button className="button button--secondary" type="button" onClick={() => void loadProfiles()}>다시 시도</button>
            </div>
          )}
          {!profilesLoading && !profilesError && profiles.length === 0 && <p role="status">현재 선택할 수 있는 사업자 유형이 없습니다.</p>}

          {!profilesLoading && !profilesError && profiles.length > 0 && (
            <fieldset className="borrower-grid">
              <legend className="sr-only">대출 계약 주체 선택</legend>
              {profiles.map((profile) => {
                const isSelected = selected === profile.businessBorrowerType
                return (
                  <label className={`borrower-card${isSelected ? ' borrower-card--selected' : ''}`} key={profile.businessBorrowerType}>
                    <input
                      type="radio"
                      name="business-borrower-type"
                      value={profile.businessBorrowerType}
                      checked={isSelected}
                      onChange={() => { setSelected(profile.businessBorrowerType); setError('') }}
                    />
                    <span className="borrower-card__marker" aria-hidden="true">{isSelected ? '✓' : ''}</span>
                    <span className="borrower-card__tag">시연용 사례</span>
                    <h2>{profile.displayName}</h2>
                    <p>{profile.description}</p>
                    <small>등록 사업자 대상 · 실제 고객 정보를 사용하지 않습니다.</small>
                  </label>
                )
              })}
            </fieldset>
          )}

          <div className="flow-actions">
            <p className="borrower-scope-note">개인 생활자금 대출과 사업자등록 전 예비창업자는 현재 지원하지 않습니다.</p>
            <p className="flow-error" role="alert" aria-live="polite">{error}</p>
            <button className="button button--primary" type="button" onClick={() => void continueToConsent()} disabled={submitting || profilesLoading}>{submitting ? '세션을 만드는 중…' : '계속하기'}</button>
          </div>
        </div>
      </main>
    </div>
  )
}

export default CustomerStartPage
