import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import Header from '../components/Header'
import { findDemoProfile } from '../data/demoProfiles'
import { customerSessionProvider } from '../mocks/customerSessionProvider'
import './DataConnectionPage.css'

function DataConnectionPage() {
  const navigate = useNavigate()
  const [session] = useState(() => customerSessionProvider.get())
  useEffect(() => { if (!session) navigate('/start', { replace: true }) }, [navigate, session])
  if (!session) return null

  const requiredComplete = Object.values(session.consents.required).every(Boolean)
  const optionalCount = Object.values(session.consents.optional).filter(Boolean).length

  return (
    <div className="workspace-shell customer-flow">
      <Header />
      <main className="connection-page">
        <div className="container connection-card">
          <span className="connection-card__badge">Demo 화면 준비 중</span>
          <p className="flow-kicker">DATA CONNECTION</p>
          <h1>고객 데이터를 연결합니다</h1>
          <p>이 화면은 다음 단계의 위치를 보여주는 placeholder입니다. 아직 실제 데이터 연결은 수행하지 않습니다.</p>
          <dl>
            <div><dt>선택한 프로필</dt><dd>{findDemoProfile(session.selectedProfileType)?.name}</dd></div>
            <div><dt>필수 동의</dt><dd>{requiredComplete ? '완료' : '미완료'}</dd></div>
            <div><dt>선택 동의</dt><dd>{optionalCount}개 선택 · 미선택 항목은 연결하지 않음</dd></div>
            <div><dt>세션</dt><dd>Demo Only · 최소 상태만 저장</dd></div>
          </dl>
          <Link className="button button--secondary" to="/consent">동의 범위 다시 보기</Link>
        </div>
      </main>
    </div>
  )
}

export default DataConnectionPage
