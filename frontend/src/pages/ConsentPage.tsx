import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import Header from '../components/Header'
import { findDemoProfile } from '../data/demoProfiles'
import { customerSessionProvider } from '../mocks/customerSessionProvider'
import { emptyConsents, type ConsentSelections } from '../types/customerSession'
import './ConsentPage.css'

const requiredItems = [
  ['customerIdentity', '은행 내부 고객확인 정보', '고객 식별과 서비스 세션 확인', '이용 은행'],
  ['accountSummary', '은행 내부 계좌·입출금 요약', '보완 평가에 필요한 요약 정보 확인', '이용 은행'],
  ['creditInformation', '은행이 정식 절차로 조회한 신용정보', '동의 범위 내 보완 평가', '이용 은행 및 정식 조회기관'],
] as const

const optionalItems = [
  ['submittedDocuments', '고객 제출 소득·사업·재무·세금 자료', '고객이 선택한 추가 자료 확인', '고객 및 이용 은행'],
  ['otherInstitutions', '고객 동의 기반 타 금융기관 정보', '연결에 동의한 금융정보 확인', '해당 금융기관 및 이용 은행'],
  ['partnerData', '카드·POS·배달 등의 외부 데이터', '제휴와 고객 동의 범위 내 정보 확인', '고객이 동의한 제휴사 및 이용 은행'],
] as const

function ConsentPage() {
  const navigate = useNavigate()
  const [session] = useState(() => customerSessionProvider.get())
  const [consents, setConsents] = useState<ConsentSelections>(() => session?.consents ?? emptyConsents())

  useEffect(() => { if (!session) navigate('/start', { replace: true }) }, [navigate, session])
  if (!session) return null

  const requiredComplete = Object.values(consents.required).every(Boolean)
  const setConsent = (group: keyof ConsentSelections, key: string, checked: boolean) => {
    setConsents((current) => ({ ...current, [group]: { ...current[group], [key]: checked } }))
  }
  const submit = () => {
    if (!requiredComplete) return
    if (customerSessionProvider.updateConsents(consents)) navigate('/data-connection')
    else navigate('/start', { replace: true })
  }

  return (
    <div className="workspace-shell customer-flow">
      <Header />
      <main className="consent-page">
        <div className="container consent-page__inner">
          <header className="consent-heading">
            <div><p className="flow-kicker">DATA CONSENT</p><h1>연결할 데이터의 이용 범위를 확인해주세요</h1><p>동의는 데이터 연결 성공과 별개의 단계이며, 선택 항목은 동의하지 않아도 계속할 수 있습니다.</p></div>
            <div className="session-summary"><span>Demo Only</span><strong>{findDemoProfile(session.selectedProfileType)?.name}</strong><small>합성 데이터 세션</small></div>
          </header>

          <fieldset className="consent-group">
            <legend><span>필수 동의</span><strong>서비스 진행에 필요합니다</strong></legend>
            {requiredItems.map(([key, name, purpose, owner]) => (
              <label className="consent-item" key={key}>
                <input type="checkbox" checked={consents.required[key]} onChange={(event) => setConsent('required', key, event.target.checked)} />
                <span className="consent-item__box" aria-hidden="true">✓</span>
                <span className="consent-item__content"><strong>{name}</strong><small><b>이용 목적</b>{purpose}</small><small><b>보유·제공 주체</b>{owner}</small><em>필수 · Demo 데이터</em></span>
              </label>
            ))}
          </fieldset>

          <fieldset className="consent-group consent-group--optional">
            <legend><span>선택 동의</span><strong>선택하지 않아도 진행할 수 있습니다</strong></legend>
            {optionalItems.map(([key, name, purpose, owner]) => (
              <label className="consent-item" key={key}>
                <input type="checkbox" checked={consents.optional[key]} onChange={(event) => setConsent('optional', key, event.target.checked)} />
                <span className="consent-item__box" aria-hidden="true">✓</span>
                <span className="consent-item__content"><strong>{name}</strong><small><b>이용 목적</b>{purpose}</small><small><b>보유·제공 주체</b>{owner}</small><em>선택 · Demo 데이터</em></span>
              </label>
            ))}
          </fieldset>

          <div className="consent-actions">
            <p aria-live="polite">{requiredComplete ? '필수 동의가 완료되었습니다.' : '계속하려면 필수 항목에 모두 동의해주세요.'}</p>
            <div><Link className="button button--secondary" to="/start">이전으로</Link><button className="button button--primary" type="button" disabled={!requiredComplete} onClick={submit}>동의하고 데이터 연결로 이동</button></div>
          </div>
        </div>
      </main>
    </div>
  )
}

export default ConsentPage
