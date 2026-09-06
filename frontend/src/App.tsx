import { useEffect, useRef } from 'react'
import { Link, Navigate, Route, Routes } from 'react-router-dom'
import './App.css'
import AdminShell from './components/AdminShell'
import Header from './components/Header'
import RouteAnnouncement from './components/RouteAnnouncement'
import AdminReviewDetailPage from './pages/AdminReviewDetailPage'
import AdminReviewListPage from './pages/AdminReviewListPage'
import AssessmentPage from './pages/AssessmentPage'
import ApplicationHandoffPage from './pages/ApplicationHandoffPage'
import ConsentPage from './pages/ConsentPage'
import CustomerStartPage from './pages/CustomerStartPage'
import DataConnectionPage from './pages/DataConnectionPage'
import EvidenceSelectionPage from './pages/EvidenceSelectionPage'
import NotFoundPage from './pages/NotFoundPage'
import ProductComparisonPage from './pages/ProductComparisonPage'
import ProductDetailPage from './pages/ProductDetailPage'

const principles = [
  { number: '01', title: '기존 평가를 먼저 확인', body: '은행의 기존 평가와 고객이 동의한 범위의 정보를 바탕으로 정책 경계 상태를 확인합니다.' },
  { number: '02', title: '필요한 증빙만 요청', body: '기존 정보로 충분하면 추가 자료를 요구하지 않고, 불확실성이 남은 경우에만 최소 증빙 한 건을 요청합니다.' },
  { number: '03', title: '검증된 결과를 그대로 설명', body: '품질 검증을 통과한 정보만 재평가에 사용하며, 프론트와 AI는 금융 판단을 만들거나 변경하지 않습니다.' },
]

const steps = [
  ['01', '사업자 유형 선택', '개인사업자 또는 법인사업자를 선택해 세션을 시작합니다.'],
  ['02', '기존 평가 확인', '은행이 보유하거나 고객 동의를 받아 확인한 데이터로 기준평가를 불러옵니다.'],
  ['03', '정책 경계 확인', 'Backend가 확정한 안정·불확실·정책상 중단 상태와 이유를 보여줍니다.'],
  ['04', '최소 증빙 재확인', '필요한 경우에만 증빙 한 건의 품질을 검증하고 반영 전후 결과를 설명합니다.'],
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
      <div className="evidence-chip chip-one"><span aria-hidden="true">✓</span><div><small>Baseline</small><strong>Existing data</strong></div></div>
      <div className="evidence-chip chip-two"><span aria-hidden="true">✓</span><div><small>Policy boundary</small><strong>Server confirmed</strong></div></div>
      <div className="evidence-chip chip-three"><span aria-hidden="true">→</span><div><small>Minimum evidence</small><strong>One at a time</strong></div></div>
    </div>
  )
}

function LandingPage() {
  return (
    <div className="site-shell">
      <Header />
      <main id="main-content" tabIndex={-1}>
        <section className="hero" id="intro"><div className="container hero__grid">
          <div className="hero__content"><p className="eyebrow">Uncertainty-based second look</p><h1>더 묻지 않고<br /><span>최소 증빙만 확인합니다</span></h1><p className="hero__description">CredAble은 사업자금 대출을 탐색하는 등록 개인사업자와 법인사업자를 대상으로, 기존 평가의 불확실성이 남은 경우에만 최소 증빙을 요청하고 검증된 정보로 재확인을 돕습니다.</p><div className="hero__actions"><Link className="button button--primary" to="/start">Demo 평가 시작</Link><a className="button button--secondary" href="#principles">서비스 원칙 보기</a></div><p className="demo-note"><span aria-hidden="true">ⓘ</span> Demo Only · 조회 결과는 실제 승인·부결이나 최종 대출 조건을 의미하지 않습니다.</p></div>
          <BrandScene />
        </div></section>
        <section className="principles" id="principles" aria-labelledby="principles-title"><div className="container"><p className="section-label">OUR PRINCIPLES</p><h2 id="principles-title">기존 평가를 존중하고,<br />필요한 정보만 확인합니다</h2><div className="principle-grid">{principles.map((item) => <article className="principle-card" key={item.number}><span>{item.number}</span><h3>{item.title}</h3><p>{item.body}</p></article>)}</div></div></section>
        <section className="process" id="process" aria-labelledby="process-title"><div className="container process__heading"><p className="section-label">HOW IT WORKS</p><h2 id="process-title">기준평가에서 정책 경계를 확인하고<br /><span>최소 증빙으로 다시 살펴봅니다</span></h2><p>경로가 안정되면 추가 수집을 멈추고, 불확실성이나 이상 징후가 남으면 심사역 검토가 필요함을 안내합니다.</p></div><div className="container step-grid">{steps.map(([number, title, body]) => <article className="step-card" key={number}><span className="step-number">{number}</span><h3>{title}</h3><p>{body}</p></article>)}</div></section>
      </main>
      <footer><div className="container footer__inner"><strong>CredAble</strong><span>Demo Only · Bank-powered complementary assessment</span></div></footer>
    </div>
  )
}

function App() {
  return <><RouteAnnouncement /><Routes><Route path="/" element={<LandingPage />} /><Route path="/start" element={<CustomerStartPage />} /><Route path="/consent" element={<ConsentPage />} /><Route path="/data-connection" element={<DataConnectionPage />} /><Route path="/assessment" element={<AssessmentPage />} /><Route path="/evidence" element={<EvidenceSelectionPage />} /><Route path="/products" element={<ProductComparisonPage />} /><Route path="/products/:productId" element={<ProductDetailPage />} /><Route path="/products/:productId/apply" element={<ApplicationHandoffPage />} /><Route path="/admin" element={<AdminShell />}><Route index element={<Navigate to="reviews" replace />} /><Route path="reviews" element={<AdminReviewListPage />} /><Route path="reviews/:reviewId" element={<AdminReviewDetailPage />} /></Route><Route path="*" element={<NotFoundPage />} /></Routes></>
}
export default App
