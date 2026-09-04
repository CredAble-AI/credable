import { useEffect, useRef } from 'react'
import { Link, Route, Routes } from 'react-router-dom'
import './App.css'
import Header from './components/Header'
import AssessmentPage from './pages/AssessmentPage'
import CaseStartPage from './pages/CaseStartPage'
import ConsentPage from './pages/ConsentPage'
import CustomerStartPage from './pages/CustomerStartPage'
import DataConnectionPage from './pages/DataConnectionPage'
import EligibilityPage from './pages/EligibilityPage'
import EvidencePage from './pages/EvidencePage'
import EvidenceQualityPage from './pages/EvidenceQualityPage'
import ProductComparisonPage from './pages/ProductComparisonPage'
import ProductDetailPage from './pages/ProductDetailPage'
import SecondLookPage from './pages/SecondLookPage'

const principles = [
  { number: '01', title: '은행이 제공하는 보완 평가', body: '은행이 보유하거나 고객 동의를 받아 확인한 데이터를 바탕으로 진행합니다.' },
  { number: '02', title: '명확한 데이터 이용 범위', body: '필수와 선택 항목을 구분하고 고객이 동의한 범위만 연결합니다.' },
  { number: '03', title: '같은 기준의 조건 비교', body: 'Backend가 확정한 자사 대출상품별 확인 가능한 조건을 같은 기준으로 보여줍니다.' },
]

const steps = [
  ['01', '고객 세션 시작', 'Demo 프로필로 데이터 연결 흐름을 시작합니다.'],
  ['02', '이용 범위 동의', '필수 데이터와 선택 데이터를 명확히 나누어 확인합니다.'],
  ['03', '금융 데이터 연결', '고객이 동의한 범위의 데이터를 안전하게 연결합니다.'],
  ['04', '상품 조건 확인', 'Backend가 확정한 확인 가능한 조건을 같은 기준으로 비교합니다.'],
]

function BrandScene() {
  const sceneRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const scene = sceneRef.current
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)')
    const finePointer = window.matchMedia('(hover: hover) and (pointer: fine)')
    if (!scene || reduceMotion.matches) return

    let targetX = 0
    let targetY = 0
    let currentX = 0
    let currentY = 0
    let scrollOffset = 0
    let frame = 0

    const render = () => {
      currentX += (targetX - currentX) * 0.06
      currentY += (targetY - currentY) * 0.06
      scene.style.setProperty('--tilt-x', `${currentY.toFixed(2)}deg`)
      scene.style.setProperty('--tilt-y', `${currentX.toFixed(2)}deg`)
      scene.style.setProperty('--parallax', `${scrollOffset.toFixed(1)}px`)
      scene.style.setProperty('--glow-parallax', `${(scrollOffset * 0.45).toFixed(1)}px`)
      frame = requestAnimationFrame(render)
    }
    const handlePointer = (event: PointerEvent) => {
      const bounds = scene.getBoundingClientRect()
      targetX = ((event.clientX - bounds.left) / bounds.width - 0.5) * 8
      targetY = -((event.clientY - bounds.top) / bounds.height - 0.5) * 8
    }
    const resetPointer = () => { targetX = 0; targetY = 0 }
    const handleScroll = () => { scrollOffset = Math.min(window.scrollY * 0.08, 38) }

    if (finePointer.matches) {
      scene.addEventListener('pointermove', handlePointer)
      scene.addEventListener('pointerleave', resetPointer)
    }
    window.addEventListener('scroll', handleScroll, { passive: true })
    handleScroll()
    frame = requestAnimationFrame(render)
    return () => {
      cancelAnimationFrame(frame)
      scene.removeEventListener('pointermove', handlePointer)
      scene.removeEventListener('pointerleave', resetPointer)
      window.removeEventListener('scroll', handleScroll)
    }
  }, [])

  return (
    <div className="brand-scene" ref={sceneRef}>
      <div className="brand-glow" aria-hidden="true" />
      <div className="orbit orbit-one" aria-hidden="true" />
      <div className="orbit orbit-two" aria-hidden="true" />
      <div className="orbit orbit-three" aria-hidden="true" />
      <div className="brand-object">
        <img src="/brand/credable-mark-3d.png" width="1280" height="1280" alt="CredAble 3D 로고" />
      </div>
      <div className="brand-reflection" aria-hidden="true" />
      <div className="evidence-chip chip-one"><span aria-hidden="true">✓</span><div><small>Bank data</small><strong>Connected</strong></div></div>
      <div className="evidence-chip chip-two"><span aria-hidden="true">✓</span><div><small>Consent</small><strong>In scope</strong></div></div>
      <div className="evidence-chip chip-three"><span aria-hidden="true">→</span><div><small>Product terms</small><strong>Comparable view</strong></div></div>
    </div>
  )
}

function LandingPage() {
  return (
    <div className="site-shell">
      <Header />
      <main>
        <section className="hero" id="intro"><div className="container hero__grid">
          <div className="hero__content"><p className="eyebrow">Bank-powered complementary credit assessment</p><h1>흩어진 금융 데이터를 연결해<br /><span>대출 조건을 한눈에 비교합니다</span></h1><p className="hero__description">CredAble은 은행이 보유하거나 고객 동의를 받아 확인한 데이터를 바탕으로 보완 평가를 수행하고, 자사 대출상품별 확인 가능한 조건을 같은 기준으로 보여줍니다.</p><div className="hero__actions"><Link className="button button--primary" to="/start">평가·상품조건 조회 시작</Link><a className="button button--secondary" href="#principles">서비스 알아보기</a></div><p className="demo-note"><span aria-hidden="true">ⓘ</span> Demo Only · 조회 결과는 실제 승인이나 최종 대출 조건을 의미하지 않습니다.</p></div>
          <BrandScene />
        </div></section>
        <section className="principles" id="principles" aria-labelledby="principles-title"><div className="container"><p className="section-label">OUR PRINCIPLES</p><h2 id="principles-title">데이터의 범위는 투명하게,<br />조건은 같은 기준으로</h2><div className="principle-grid">{principles.map((item) => <article className="principle-card" key={item.number}><span>{item.number}</span><h3>{item.title}</h3><p>{item.body}</p></article>)}</div></div></section>
        <section className="process" id="process" aria-labelledby="process-title"><div className="container process__heading"><p className="section-label">HOW IT WORKS</p><h2 id="process-title">동의한 데이터를 연결하고<br /><span>확인 가능한 조건을 비교합니다</span></h2><p>세션 시작부터 조건 확인까지, 고객이 확인한 범위를 중심으로 이어집니다.</p></div><div className="container step-grid">{steps.map(([number, title, body]) => <article className="step-card" key={number}><span className="step-number">{number}</span><h3>{title}</h3><p>{body}</p></article>)}</div></section>
      </main>
      <footer><div className="container footer__inner"><strong>CredAble</strong><span>Demo Only · Bank-powered complementary assessment</span></div></footer>
    </div>
  )
}

function App() {
  return <Routes><Route path="/" element={<LandingPage />} /><Route path="/start" element={<CustomerStartPage />} /><Route path="/consent" element={<ConsentPage />} /><Route path="/data-connection" element={<DataConnectionPage />} /><Route path="/assessment" element={<AssessmentPage />} /><Route path="/products" element={<ProductComparisonPage />} /><Route path="/products/:productId" element={<ProductDetailPage />} /><Route path="/case" element={<CaseStartPage />} /><Route path="/eligibility" element={<EligibilityPage />} /><Route path="/evidence" element={<EvidencePage />} /><Route path="/evidence-quality" element={<EvidenceQualityPage />} /><Route path="/second-look" element={<SecondLookPage />} /></Routes>
}
export default App
