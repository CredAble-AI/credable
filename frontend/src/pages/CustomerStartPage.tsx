import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { normalizeSessionError } from '../api/sessionClient'
import Header from '../components/Header'
import { sessionProvider } from '../hooks/useCustomerSession'
import type { ApiError } from '../types/api'
import type { DemoProfile } from '../types/customerSession'
import './CustomerStartPage.css'

function CustomerStartPage() {
  const navigate = useNavigate()
  const [profiles, setProfiles] = useState<DemoProfile[]>([])
  const [profilesLoading, setProfilesLoading] = useState(true)
  const [profilesError, setProfilesError] = useState<ApiError | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
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
      setError('계속하려면 Demo 프로필을 하나 선택해주세요.')
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
      <main className="customer-page">
        <div className="container customer-page__inner">
          <div className="flow-heading">
            <p className="flow-kicker">NEW CUSTOMER SESSION</p>
            <span className="demo-badge"><i aria-hidden="true" />Demo Only</span>
            <h1>어떤 Demo로 시작할까요?</h1>
            <p>아래 프로필은 서비스 흐름을 확인하기 위한 대표 사례입니다. 실제 이용 대상은 특정 고객 유형으로 제한되지 않습니다.</p>
          </div>

          {profilesLoading && <p role="status" aria-live="polite">Demo 프로필을 불러오고 있습니다.</p>}
          {profilesError && (
            <div className="flow-actions">
              <p className="flow-error" role="alert">{profilesError.message}</p>
              <button className="button button--secondary" type="button" onClick={() => void loadProfiles()}>다시 시도</button>
            </div>
          )}
          {!profilesLoading && !profilesError && profiles.length === 0 && <p role="status">현재 선택할 수 있는 Demo 프로필이 없습니다.</p>}

          {!profilesLoading && !profilesError && profiles.length > 0 && (
            <fieldset className="profile-grid">
              <legend className="sr-only">Demo 프로필 선택</legend>
              {profiles.map((profile) => {
                const isSelected = selected === profile.demoProfileId
                return (
                  <label className={`profile-card${isSelected ? ' profile-card--selected' : ''}`} key={profile.demoProfileId}>
                    <input
                      type="radio"
                      name="demo-profile"
                      value={profile.demoProfileId}
                      checked={isSelected}
                      onChange={() => { setSelected(profile.demoProfileId); setError('') }}
                    />
                    <span className="profile-card__marker" aria-hidden="true">{isSelected ? '✓' : ''}</span>
                    <span className="profile-card__tag">Synthetic profile</span>
                    <h2>{profile.displayName}</h2>
                    <p>{profile.description}</p>
                    <small>합성 데이터 · 실제 정보를 사용하지 않습니다.</small>
                  </label>
                )
              })}
            </fieldset>
          )}

          <div className="flow-actions">
            <p className="flow-error" role="alert" aria-live="polite">{error}</p>
            <button className="button button--primary" type="button" onClick={() => void continueToConsent()} disabled={submitting || profilesLoading}>{submitting ? '세션을 만드는 중…' : '계속하기'}</button>
          </div>
        </div>
      </main>
    </div>
  )
}

export default CustomerStartPage
