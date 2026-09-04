import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Header from '../components/Header'
import { demoProfiles } from '../data/demoProfiles'
import { customerSessionProvider } from '../mocks/customerSessionProvider'
import type { DemoProfileType } from '../types/customerSession'
import './CustomerStartPage.css'

function CustomerStartPage() {
  const navigate = useNavigate()
  const [selected, setSelected] = useState<DemoProfileType | null>(null)
  const [error, setError] = useState('')

  const continueToConsent = () => {
    if (!selected) {
      setError('계속하려면 Demo 프로필을 하나 선택해주세요.')
      return
    }
    customerSessionProvider.create(selected)
    navigate('/consent')
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

          <fieldset className="profile-grid">
            <legend className="sr-only">Demo 프로필 선택</legend>
            {demoProfiles.map((profile) => {
              const isSelected = selected === profile.type
              return (
                <label className={`profile-card${isSelected ? ' profile-card--selected' : ''}`} key={profile.type}>
                  <input
                    type="radio"
                    name="demo-profile"
                    value={profile.type}
                    checked={isSelected}
                    onChange={() => { setSelected(profile.type); setError('') }}
                  />
                  <span className="profile-card__marker" aria-hidden="true">{isSelected ? '✓' : ''}</span>
                  <span className="profile-card__tag">Synthetic profile</span>
                  <h2>{profile.name}</h2>
                  <p>{profile.description}</p>
                  <small>{profile.context}</small>
                </label>
              )
            })}
          </fieldset>

          <div className="flow-actions">
            <p className="flow-error" role="alert" aria-live="polite">{error}</p>
            <button className="button button--primary" type="button" onClick={continueToConsent}>계속하기</button>
          </div>
        </div>
      </main>
    </div>
  )
}

export default CustomerStartPage
