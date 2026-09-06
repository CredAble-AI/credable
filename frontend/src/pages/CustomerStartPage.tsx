import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { normalizeSessionError } from '../api/sessionClient'
import CustomerFlowSteps from '../components/CustomerFlowSteps'
import Header from '../components/Header'
import { sessionProvider } from '../hooks/useCustomerSession'
import type { ApiError } from '../types/api'
import type { BusinessBorrowerType, DemoProfile } from '../types/customerSession'
import './CustomerStartPage.css'

const borrowerDescriptions: Record<BusinessBorrowerType, string> = {
  SOLE_PROPRIETOR: '사업소득과 상환 책임의 주체가 개인인 등록 사업자입니다.',
  CORPORATION: '법인 명의로 사업자금 대출 계약과 평가가 진행되는 등록 법인입니다.',
}

function CustomerStartPage() {
  const navigate = useNavigate()
  const [profiles, setProfiles] = useState<DemoProfile[]>([])
  const [profilesLoading, setProfilesLoading] = useState(true)
  const [profilesError, setProfilesError] = useState<ApiError | null>(null)
  const [selected, setSelected] = useState<BusinessBorrowerType | null>(null)
  const [selectedProfileId, setSelectedProfileId] = useState<string | null>(null)
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
    if (!selectedProfileId) {
      setError('확인할 시연 사례를 선택해주세요.')
      return
    }
    setSubmitting(true)
    setError('')
    try {
      await sessionProvider.create(selectedProfileId, new AbortController().signal)
      navigate('/consent')
    } catch (caught) {
      setError(normalizeSessionError(caught).message)
    } finally {
      setSubmitting(false)
    }
  }

  const profilesByType = profiles.reduce<Record<BusinessBorrowerType, DemoProfile[]>>((grouped, profile) => {
    (grouped[profile.businessBorrowerType] ??= []).push(profile)
    return grouped
  }, {} as Record<BusinessBorrowerType, DemoProfile[]>)
  const borrowerTypes = Object.keys(profilesByType) as BusinessBorrowerType[]

  return (
    <div className="workspace-shell customer-flow">
      <Header />
      <main id="main-content" tabIndex={-1} className="customer-page">
        <div className="container customer-page__inner">
          <CustomerFlowSteps current="start" className="customer-progress customer-progress--dark" />
          <div className="flow-heading">
            <h1 className="page-title-lines"><span>대출 계약의</span><span>주체를 선택해주세요</span></h1>
            <p>CredAble은 사업자금 대출을 탐색하는 등록 사업자를 위한 서비스입니다. 개인사업자와 법인사업자는 실제 서비스 대상 분기이며, 유형에 따라 평가 주체와 사용하는 데이터를 구분합니다.</p>
          </div>

          {profilesLoading && <p role="status" aria-live="polite">사업자 유형을 불러오고 있습니다.</p>}
          {profilesError && (
            <div className="flow-actions">
              <p className="flow-error" role="alert">{profilesError.message}</p>
              <button className="button button--secondary" type="button" onClick={() => void loadProfiles()}>다시 시도</button>
            </div>
          )}
          {!profilesLoading && !profilesError && profiles.length === 0 && <p role="status">현재 선택할 수 있는 사업자 유형이 없습니다.</p>}

          {!profilesLoading && !profilesError && profiles.length > 0 && (
            <>
              <fieldset className="borrower-grid">
                <legend className="sr-only">대출 계약 주체 선택</legend>
                {borrowerTypes.map((borrowerType) => {
                  const isSelected = selected === borrowerType
                  const [first] = profilesByType[borrowerType]
                  return (
                    <label className={`borrower-card${isSelected ? ' borrower-card--selected' : ''}`} key={borrowerType}>
                      <input
                        type="radio"
                        name="business-borrower-type"
                        value={borrowerType}
                        checked={isSelected}
                        onChange={() => { setSelected(borrowerType); setSelectedProfileId(first.demoProfileId); setError('') }}
                      />
                      <span className="borrower-card__marker" aria-hidden="true">{isSelected ? '✓' : ''}</span>
                      <span className="borrower-card__tag">서비스 대상</span>
                      <h2>{first.displayName}</h2>
                      <p>{borrowerDescriptions[borrowerType]}</p>
                      <small>선택한 유형에 맞춰 평가 주체와 사용 데이터를 구분합니다.</small>
                    </label>
                  )
                })}
              </fieldset>

              {selected && (
                <fieldset className="scenario-picker">
                  <legend><span className="scenario-picker__tag">DEMO</span> 확인할 시연 사례를 선택해주세요</legend>
                  <p className="scenario-picker__note">실제 서비스에서는 고객의 기존 평가 결과에 따라 상태가 정해집니다. 공모전 시연에서는 정책 경계 상태별 흐름을 직접 확인할 수 있도록 합성 사례를 골라 시작합니다.</p>
                  {profilesByType[selected].map((profile) => {
                    const isSelected = selectedProfileId === profile.demoProfileId
                    return (
                      <label className={`scenario-option${isSelected ? ' scenario-option--selected' : ''}`} key={profile.demoProfileId}>
                        <input
                          type="radio"
                          name="demo-profile-id"
                          value={profile.demoProfileId}
                          checked={isSelected}
                          onChange={() => { setSelectedProfileId(profile.demoProfileId); setError('') }}
                        />
                        <span><strong>{profile.scenarioLabel}</strong><small>{profile.description}</small><p>{profile.scenarioSummary}</p></span>
                      </label>
                    )
                  })}
                </fieldset>
              )}
            </>
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
