import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Header from '../components/Header'
import { findDemoProfile } from '../data/demoProfiles'
import { customerSessionProvider } from '../mocks/customerSessionProvider'
import './DataConnectionPage.css'

function AssessmentPage() {
  const navigate = useNavigate()
  const [session] = useState(() => customerSessionProvider.get())
  const requiredComplete = session ? Object.values(session.consents.required).every(Boolean) : false
  useEffect(() => {
    if (!session) navigate('/start', { replace: true })
    else if (!requiredComplete) navigate('/consent', { replace: true })
  }, [navigate, requiredComplete, session])
  if (!session || !requiredComplete) return null
  return <div className="workspace-shell customer-flow"><Header /><main className="connection-page"><div className="container connection-page__inner"><nav className="flow-steps" aria-label="진행 단계"><span>시작</span><span>동의</span><span>데이터 연결</span><strong aria-current="step">보완 평가</strong><span>상품 비교</span></nav><section className="empty-sources assessment-placeholder"><span className="connection-badge">Demo Only</span><p className="flow-kicker">COMPLEMENTARY ASSESSMENT</p><h1>보완 평가 결과를 준비하고 있습니다</h1><p>{findDemoProfile(session.selectedProfileType)?.name} · 다음 작업에서 구현됩니다.</p></section></div></main></div>
}

export default AssessmentPage
