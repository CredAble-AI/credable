import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Header from '../components/Header'
import { findDemoProfile } from '../data/demoProfiles'
import { customerSessionProvider } from '../mocks/customerSessionProvider'
import './AssessmentPage.css'

function ProductComparisonPage() {
  const navigate = useNavigate()
  const [session] = useState(() => customerSessionProvider.get())
  const requiredComplete = session ? Object.values(session.consents.required).every(Boolean) : false
  useEffect(() => {
    if (!session) navigate('/start', { replace: true })
    else if (!requiredComplete) navigate('/consent', { replace: true })
  }, [navigate, requiredComplete, session])
  if (!session || !requiredComplete) return null
  return <div className="workspace-shell customer-flow"><Header /><main className="assessment-page"><div className="container assessment-page__inner"><nav className="assessment-steps" aria-label="진행 단계"><span>시작</span><span>동의</span><span>데이터 연결</span><span>보완 평가</span><strong aria-current="step">상품 비교</strong></nav><section className="assessment-result product-placeholder"><div className="assessment-result__icon" aria-hidden="true">→</div><div><span>Demo Only</span><h1>자사 대출상품 조건을 비교합니다</h1><p>{findDemoProfile(session.selectedProfileType)?.name} · 다음 작업에서 구현됩니다.</p><small>특정 상품을 자동으로 선택하지 않습니다.</small></div></section></div></main></div>
}

export default ProductComparisonPage
